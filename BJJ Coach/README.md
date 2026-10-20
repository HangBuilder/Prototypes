# BJJ Coach — local video PoC

Turn a user-owned recording into reviewable evidence before building a technique
library. This is a Python CLI and a local review page, not the full application.
There is no hosted service, paid API, automatic coaching, or footage upload.

## Install

Python 3.11+ and `ffmpeg`/`ffprobe` on PATH are required. Use this existing checkout;
no worktree is needed. Commands below run from the `BJJ Coach` project directory.

```sh
python3 -m venv .venv
source .venv/bin/activate
# Apple Silicon Mac (MLX); see the Linux alternative below.
python -m pip install -e '.[mac]'
```

On Linux/Intel, instead install `python -m pip install -e '.[cpu]'` for CPU/int8
faster-whisper. Top-level dependencies are pinned in `pyproject.toml`;
`requirements-linux-tested.txt` records the exact installed Linux environment,
not a cross-platform lockfile or a claim that MLX was tested here. To reproduce the
Linux environment, install that file first, then `python -m pip install -e .`.

Before processing on a Mac, inspect `uname -m`, `sw_vers`, `sysctl -n hw.memsize`,
`df -h .`, `python3 --version`, and `ffmpeg -version`. MLX requires macOS/arm64.
Start with `mlx-community/whisper-tiny` for a short trial, then select a larger
model only after listening and checking time/memory. The M4 Mac's RAM and OS have
not been inspected from this Linux cloud machine. Do not install system packages
blindly: if FFmpeg is missing on a Mac with Homebrew, `brew install ffmpeg` changes
the system tool installation; review that command before running it yourself.

First inference downloads public model weights from Hugging Face. It does not
upload the input. Subsequent runs can use a local model directory with `--model`.
Default downloads are cached under the output directory's `.model-cache` unless
`HF_HOME` is already configured. For exact model reproduction, supply an immutable
Hugging Face commit with `--model-revision` or retain the same local weights.
Model identifiers without a revision can change remotely.

## Process your recording

Keep originals outside Git, e.g. in ignored `data/`. No path is hard-coded:

```sh
bjj-coach prepare '/path/to/IMG_6970.MOV' --output runs
```

The command prints a run directory named after the source SHA-256. Use that path
in place of `runs/HASH` below. `metadata.json` retains the complete ffprobe report
(codecs, channel layout/rate, rotation, embedded candidate dates/location).
`manifest.json` records source hash, confirmed metadata (initially null), stage
settings, tool versions, timing, failures, and artifact hashes. The original is
never overwritten. Run commands sequentially for each run directory; concurrent
pipeline writers to the same directory are not supported.

`reference.wav` is unfiltered floating-point PCM preserving source sample rate
and channels. `baseline.wav` is a **provisional** mono 16 kHz downmix, not an audio
quality improvement. Listen to the reference and a short baseline sample before
accepting it. Audio/video start offset is recorded; the baseline is padded or
trimmed to the video-relative timeline. The reference retains its original
samples and therefore may start at a different offset. Negative/positive offsets
must be spot-checked with the actual recording. Multi-audio-stream inputs may use
`--audio-stream N` (zero-based among audio streams). Automatic channel quality
selection is not implemented.

Sparse frames use FFmpeg autorotation, a default 30-second interval, and a cap of
60 frames. Override with `--frame-interval 5 --max-frames 100` for review; frames do
not establish motion. Full-video clips around ambiguity remain a manual step.

```sh
# On your Apple Silicon Mac: sample BEFORE full inference.
bjj-coach transcribe runs/HASH --backend mlx --model mlx-community/whisper-tiny --sample-seconds 30
# Linux equivalent:
bjj-coach transcribe runs/HASH --backend faster-whisper --model tiny --sample-seconds 30
```

Language defaults to English; use `--language` if needed. No word timings or
speaker identity are claimed. Temperature is zero and previous-text conditioning
is disabled; settings and optional `--prompt` glossary are recorded. Keep the
initial baseline free of glossary bias. Sample runs cover the beginning of the
recording; the review page can inspect difficult spans throughout a full run.

After listening to the sample, omit `--sample-seconds` to transcribe the full
file. A different settings hash creates a separate ASR run instead of overwriting
an earlier one. Outputs: `.raw.json`, normalized timestamped `.json`, `.txt`, and
`.srt`. Silence and low-score flags prompt review; they are not accuracy scores.

```sh
# Optional candidate; evaluate before accepting the filter for your gym audio.
bjj-coach enhance runs/HASH
bjj-coach transcribe runs/HASH --backend mlx --model mlx-community/whisper-tiny --variant enhanced
# Use the SAME backend/model/revision/language/prompt/sample options as baseline.
```

The candidate uses `highpass=f=80,loudnorm=I=-20:TP=-2:LRA=11`. It is conservative
but may still hurt speech; no benefit has been established. Compare difficult
passages by human listening. Two matching outputs are not proof of correctness.
Do not invent words that remain inaudible.

## Review and correct

```sh
# Optional if the original MOV codec will not play in your browser:
bjj-coach preview runs/HASH
bjj-coach review runs/HASH --port 8765
```

Open your **local machine's** browser at loopback port 8765. The server binds only
to 127.0.0.1 and is intended for one trusted local user. Cloud onboarding does not
provide a user-facing localhost preview. The UI includes video seeking, audio
comparison, timestamped transcript edits, unclear flags, frames, and a structured
candidate tags/claims editor. Save appends transcript correction history and keeps
machine output unchanged. Claims edits are schema-validated and stored separately
in `reviewed-claims.json` plus `claims-review-history.json`. No account or reviewer
authentication exists; instructor verification must be obtained separately.

`claims.json` starts with an empty segment list. This is intentionally **not** a
technique analysis. Fill segments/claims only after listening/viewing, using
`bjj_coach/claims.schema.json` and [the ontology notes](docs/ONTOLOGY.md). Direct
spoken claims require a transcript ID, an exact excerpt, and matching timestamps;
visual claims require a timestamped frame. Inferences and unsupported claims must
be labeled. Structural validation does not prove a claim is true.

```sh
bjj-coach validate runs/HASH
python -m unittest discover -s tests -v
```

Use the review editor's Validate & save button for reviewed claims; the CLI
validates the machine `claims.json`. Select representative easy/difficult/silent
spans, correct a reference transcript, and assess missed details and technique
names. WER requires that human reference; no accuracy percentage is supplied.

Stages reuse outputs only when settings and artifact hashes match. Corrupt
outputs are regenerated. Keep the original available for playback and reprocessing.
Changing extraction settings can replace derived audio/frames; existing ASR output
remains historical with its input hash. Do not change frames after attaching
visual claims without re-reviewing those claims. Preserve `runs/` backups to retain
human corrections; deleting caches/derived output can delete that local work.

## Status and limits

See [POC_FINDINGS.md](POC_FINDINGS.md) for measured results and blockers. No actual
IMG_6970.MOV metadata, transcript, visual interpretation, or audio comparison has
been produced. The cloud attachment exceeds the available 32 MiB transfer limit;
the Mac can process the original directly using its local path. Cloud model
retrieval was separately blocked by a network proxy 403 for Hugging Face.

Draft SQL lives in `schemas/001_draft.sql` and is not applied automatically. Search,
curated taxonomy ingestion, canonical knowledge, and a full app come after this
experiment demonstrates useful evidence extraction.
