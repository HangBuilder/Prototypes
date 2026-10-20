import argparse
from pathlib import Path
import sys

from .pipeline import prepare, enhance, enhanced_video, transcribe, validate_claims, read_json, stage, run, sha256


def main():
    parser = argparse.ArgumentParser(description="BJJ Coach — local video evidence PoC")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare", help="Probe, extract reference/mono audio, and sparse rotated frames")
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, default=Path("runs"))
    p.add_argument("--audio-stream", type=int, default=0)
    p.add_argument("--frame-interval", type=float, default=30)
    p.add_argument("--max-frames", type=int, default=60)
    for name in ("enhance", "preview", "validate", "review", "transcribe"):
        p = commands.add_parser(name)
        p.add_argument("run", type=Path)
        if name == "review":
            p.add_argument("--port", type=int, default=8765)
        elif name == "preview":
            p.add_argument("--audio", choices=("original", "enhanced"), default="original")
        elif name == "transcribe":
            p.add_argument("--variant", choices=("baseline", "enhanced"), default="baseline")
            p.add_argument("--backend", choices=("mlx", "faster-whisper"), default="faster-whisper")
            p.add_argument("--model")
            p.add_argument("--model-revision", help="Optional Hugging Face commit for reproducible weights")
            p.add_argument("--language", default="en", help="Explicit language; default English")
            p.add_argument("--prompt", help="Optional recorded glossary; biases output, so baseline should omit it")
            p.add_argument("--sample-seconds", type=float)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.input, args.output, args.audio_stream, args.frame_interval, args.max_frames))
        elif args.command == "enhance":
            enhance(args.run)
        elif args.command == "validate":
            claims = validate_claims(args.run)
            print(f"Valid: {len(claims['segments'])} instructional segments (empty is not an analysis)")
        elif args.command == "review":
            from .review import serve
            serve(args.run, args.port)
        elif args.command == "preview":
            if args.audio == "enhanced":
                print(enhanced_video(args.run))
                return
            manifest = read_json(args.run / "manifest.json")
            source = Path(manifest["source_path"])
            if sha256(source) != manifest["source_sha256"]:
                raise ValueError("Source changed since extraction")
            stage(args.run, manifest, "preview", {"source": manifest["source_sha256"], "codec": "h264/aac", "crf": 23},
                  ["preview.mp4"], lambda: run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", source,
                    "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-threads", "2", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", args.run / "preview.mp4"]))
        elif args.command == "transcribe":
            print(transcribe(args.run, args.variant, args.backend, args.model, args.language, args.prompt,
                             args.sample_seconds, args.model_revision))
    except Exception as exc:
        # Optional backends have their own network/runtime exception types.
        # Preserve a failing exit status and a useful error without a long traceback.
        parser.exit(1, f"Error ({type(exc).__name__}): {exc}\n")


if __name__ == "__main__":
    main()
