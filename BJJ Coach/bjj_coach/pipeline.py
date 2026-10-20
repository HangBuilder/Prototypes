"""Resumable local pipeline. No media is sent to a remote inference service."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time
from datetime import datetime, timezone

PIPELINE_VERSION = 1
ENHANCEMENT = "highpass=f=80,loudnorm=I=-20:TP=-2:LRA=11"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr[-6000:]}")
    return result.stdout


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def artifacts_valid(root, record):
    return bool(record and record.get("status") == "complete" and all(
        (root / name).is_file() and sha256(root / name) == digest
        for name, digest in record.get("artifacts", {}).items()
    ))


def stage(root, manifest, name, settings, outputs, action):
    settings = {"pipeline_version": PIPELINE_VERSION, **settings}
    previous = manifest["stages"].get(name)
    if previous and previous.get("settings") == settings and artifacts_valid(root, previous):
        return
    began = time.monotonic()
    record = {"settings": settings, "status": "running", "started_at": now(),
              "runtime": manifest.get("runtime", {})}
    manifest["stages"][name] = record
    write_json(root / "manifest.json", manifest)
    try:
        action()
        record.update(status="complete", elapsed_seconds=round(time.monotonic() - began, 3),
                      artifacts={name: sha256(root / name) for name in outputs}, finished_at=now())
    except Exception as exc:
        record.update(status="failed", error=str(exc), elapsed_seconds=round(time.monotonic() - began, 3))
        raise
    finally:
        write_json(root / "manifest.json", manifest)


def prepare(source, output, audio_stream=0, frame_interval=30.0, max_frames=60):
    source = Path(source).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Input must be a file")
    if frame_interval <= 0 or max_frames < 0:
        raise ValueError("frame-interval must be positive; max-frames must be nonnegative")
    source_hash = sha256(source)
    root = Path(output).resolve() / source_hash
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {
        "pipeline_version": PIPELINE_VERSION, "source_sha256": source_hash,
        "created_at": now(), "stages": {},
        "confirmed_metadata": {"instructor": None, "recording_date": None, "location": None},
    }
    if manifest["source_sha256"] != source_hash or manifest["pipeline_version"] != PIPELINE_VERSION:
        raise ValueError("Incompatible manifest")
    manifest["source_path"] = str(source)
    manifest["runtime"] = {"platform": platform.platform(), "python": platform.python_version(),
                           "ffmpeg": run(["ffmpeg", "-version"]).splitlines()[0]}
    metadata = probe(source)
    duration = float(metadata["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Input duration must be finite and positive")
    manifest["duration"] = duration
    # Full probe preserves codec, original channels/rate, tags, and rotation side data.
    write_json(root / "metadata.json", {"probe": metadata,
        "warning": "Embedded dates/location are unconfirmed candidates. File mtime is not recording time."})
    audio = [s for s in metadata["streams"] if s["codec_type"] == "audio"]
    if audio_stream < 0 or audio_stream >= len(audio):
        raise ValueError("Requested audio stream is absent; choose an existing --audio-stream")
    chosen = audio[audio_stream]
    audio_offset = float(chosen.get("start_time", metadata["format"].get("start_time", 0))) - float(metadata["format"].get("start_time", 0))
    manifest["audio_alignment"] = {"reference_offset_seconds": audio_offset,
        "baseline_timeline": "video-relative; silence padded or leading audio trimmed when necessary"}
    base = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", source,
            "-map", f"0:{chosen['index']}", "-vn"]
    settings = {"stream": chosen["index"], "codec": "pcm_f32le", "sample_rate": chosen["sample_rate"],
                "channels": chosen["channels"]}
    stage(root, manifest, "reference_audio", settings, ["reference.wav"],
          lambda: run(base + ["-c:a", "pcm_f32le", root / "reference.wav"]))
    alignment = (["-af", f"adelay={audio_offset * 1000:.3f}:all=1"] if audio_offset > .0005 else
                 ["-af", f"atrim=start={-audio_offset:.6f},asetpts=PTS-STARTPTS"] if audio_offset < -.0005 else [])
    stage(root, manifest, "baseline_audio", {"reference": sha256(root / "reference.wav"),
          "rate": 16000, "channels": 1, "codec": "pcm_s16le", "audio_offset_seconds": audio_offset}, ["baseline.wav"],
          lambda: run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", root / "reference.wav",
                       *alignment, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", root / "baseline.wav"]))
    video = [s for s in metadata["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
    count = min(max_frames, math.ceil(duration / frame_interval)) if video else 0
    frame_names = [f"frames/{i:04d}.jpg" for i in range(count)]
    def extract_frames():
        (root / "frames").mkdir(exist_ok=True)
        frames = []
        for i, name in enumerate(frame_names):
            timestamp = i * frame_interval
            run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(timestamp), "-i", source,
                 "-map", f"0:{video[0]['index']}", "-frames:v", "1", "-vf", "scale=640:-2", root / name])
            frames.append({"id": name, "time": timestamp, "path": name})
        write_json(root / "frames.json", frames)
    stage(root, manifest, "frames", {"interval": frame_interval, "max_frames": max_frames,
          "rotation": "FFmpeg default autorotation", "video_stream": video[0]["index"] if video else None},
          ["frames.json"] + frame_names, extract_frames)
    claims_path = root / "claims.json"
    if not claims_path.exists():
        write_json(claims_path, {"video_sha256": source_hash, "segments": []})
    write_json(manifest_path, manifest)
    return root


def enhance(root):
    root = Path(root)
    manifest = read_json(root / "manifest.json")
    stage(root, manifest, "enhanced_audio", {"input": sha256(root / "baseline.wav"), "filter": ENHANCEMENT},
          ["enhanced.wav"], lambda: run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i",
            root / "baseline.wav", "-af", ENHANCEMENT, "-ar", "16000", "-c:a", "pcm_s16le", root / "enhanced.wav"]))


def subtitle_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def transcribe(root, variant="baseline", backend="faster-whisper", model=None, language="en", prompt=None,
               sample_seconds=None, model_revision=None):
    root = Path(root)
    manifest = read_json(root / "manifest.json")
    if sample_seconds is not None and (not math.isfinite(sample_seconds) or sample_seconds <= 0):
        raise ValueError("sample-seconds must be positive and finite")
    audio = root / f"{variant}.wav"
    if not audio.is_file():
        raise ValueError(f"Missing {audio.name}; run prepare/enhance first")
    model = model or ("mlx-community/whisper-tiny" if backend == "mlx" else "tiny")
    package = "mlx-whisper" if backend == "mlx" else "faster-whisper"
    version = importlib.metadata.version(package)
    if backend == "mlx" and (platform.system() != "Darwin" or platform.machine() != "arm64"):
        raise ValueError("MLX requires Apple Silicon macOS; use faster-whisper here")
    settings = {"audio_sha256": sha256(audio), "backend": backend, "package_version": version,
                "model": model, "model_revision": model_revision, "language": language,
                "initial_prompt": prompt, "temperature": 0, "word_timestamps": False,
                "condition_on_previous_text": False, "sample_seconds": sample_seconds,
                "beam_size": 5 if backend == "faster-whisper" else None,
                "compute_type": "int8" if backend == "faster-whisper" else "backend_default"}
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
    prefix = f"asr/{variant}-{key}"
    outputs = [prefix + ext for ext in (".raw.json", ".json", ".txt", ".srt")]
    def execute():
        from dataclasses import asdict
        os.environ.setdefault("HF_HOME", str(root.parent / ".model-cache"))
        audio_input = audio
        if sample_seconds:
            audio_input = root / f"asr/{variant}-{key}.sample.wav"
            audio_input.parent.mkdir(exist_ok=True)
            run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", audio, "-t", str(sample_seconds), audio_input])
        if backend == "mlx":
            import mlx_whisper
            if model_revision:
                from huggingface_hub import snapshot_download
                local_model = snapshot_download(model, revision=model_revision)
            else:
                local_model = model
            raw = mlx_whisper.transcribe(str(audio_input), path_or_hf_repo=local_model, language=language,
                initial_prompt=prompt, temperature=0, word_timestamps=False, condition_on_previous_text=False)
            segments = raw["segments"]
        else:
            from faster_whisper import WhisperModel
            engine = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=min(4, os.cpu_count() or 1),
                                  revision=model_revision)
            iterator, info = engine.transcribe(str(audio_input), language=language, initial_prompt=prompt,
                temperature=0, beam_size=5, word_timestamps=False, condition_on_previous_text=False)
            segments = [asdict(segment) for segment in iterator]
            raw = {"segments": segments, "info": asdict(info)}
        (root / "asr").mkdir(exist_ok=True)
        write_json(root / outputs[0], raw)
        normalized = []
        limit = min(sample_seconds or manifest["duration"], manifest["duration"])
        for i, segment in enumerate(segments):
            start, end = float(segment["start"]), float(segment["end"])
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < limit and start < end):
                continue
            flags = []
            if segment.get("no_speech_prob", 0) > .5:
                flags.append("possible_silence_hallucination")
            if segment.get("avg_logprob", 0) < -1:
                flags.append("low_model_score_requires_listening")
            normalized.append({"id": f"{variant}-{key}-{i}", "start": start, "end": min(end, limit),
                "text": segment["text"].strip(), "flags": flags, "review_status": "machine_proposed"})
        write_json(root / outputs[1], {"settings": settings, "timing_granularity": "segment", "segments": normalized,
                   "warning": "Scores/flags are not calibrated accuracy. Speaker identity unknown."})
        (root / outputs[2]).write_text("\n".join(f"[{s['start']:.2f}–{s['end']:.2f}] {s['text']}" for s in normalized) + "\n")
        (root / outputs[3]).write_text("\n\n".join(f"{i+1}\n{subtitle_time(s['start'])} --> {subtitle_time(s['end'])}\n{s['text']}"
                                               for i, s in enumerate(normalized)) + "\n")
    stage(root, manifest, prefix, settings, outputs, execute)
    return root / outputs[1]


def validate_claims(root, claims_path=None):
    from jsonschema import Draft202012Validator
    root = Path(root)
    claims = read_json(claims_path or root / "claims.json")
    schema = read_json(Path(__file__).with_name("claims.schema.json"))
    Draft202012Validator(schema).validate(claims)
    manifest = read_json(root / "manifest.json")
    if claims["video_sha256"] != manifest["source_sha256"]:
        raise ValueError("Claims refer to a different source")
    duration = manifest["duration"]
    frames = {f["id"]: f for f in read_json(root / "frames.json")}
    transcripts = {}
    for name, record in manifest["stages"].items():
        if name.startswith("asr/") and artifacts_valid(root, record):
            for segment in read_json(root / f"{name}.json")["segments"]:
                transcripts[segment["id"]] = segment
    seen = set()
    def unique(identifier):
        if identifier in seen:
            raise ValueError(f"Duplicate ID: {identifier}")
        seen.add(identifier)
    for segment in claims["segments"]:
        unique(segment["id"])
        if not 0 <= segment["start"] < segment["end"] <= duration:
            raise ValueError("Invalid segment boundaries")
        for claim in segment["claims"]:
            unique(claim["id"])
            if claim["basis"] in ("spoken", "visual") and not claim["evidence"]:
                raise ValueError("Direct claims require evidence")
            if claim["kind"] == "execution_step" and "step_index" not in claim:
                raise ValueError("Execution steps need step_index")
            if claim["basis"] in ("inferred", "unsupported") and claim["review_status"] == "instructor_verified":
                raise ValueError("Inferred/unsupported claims cannot be instructor verified")
            for evidence in claim["evidence"]:
                if not segment["start"] <= evidence["start"] <= evidence["end"] <= segment["end"]:
                    raise ValueError("Evidence must lie inside its segment")
                if claim["basis"] in ("spoken", "visual") and evidence["basis"] != claim["basis"]:
                    raise ValueError("Evidence basis does not match direct claim")
                reference = evidence["reference"]
                if evidence["basis"] == "spoken":
                    target = transcripts.get(reference)
                    if not target or evidence["excerpt"] not in target["text"]:
                        raise ValueError("Spoken evidence must quote an existing transcript segment")
                    if not target["start"] <= evidence["start"] < evidence["end"] <= target["end"]:
                        raise ValueError("Spoken evidence must lie inside referenced transcript span")
                elif reference not in frames or not evidence["start"] <= frames[reference]["time"] <= evidence["end"]:
                    raise ValueError("Visual evidence must reference an included timestamped frame")
    return claims
