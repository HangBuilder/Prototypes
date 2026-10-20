"""Loopback-only review server, including byte ranges for video seeking."""
import hmac
import json
import mimetypes
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .pipeline import artifacts_valid, now, read_json, validate_claims, write_json, sha256


def serve(root, port=8765):
    root = Path(root).resolve()
    manifest = read_json(root / "manifest.json")
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()

    def has_enhanced_video():
        current = read_json(root / "manifest.json")
        record = current["stages"].get("enhanced_video")
        return bool(artifacts_valid(root, record) and (root / "enhanced.wav").is_file()
                    and record["settings"]["audio_sha256"] == sha256(root / "enhanced.wav"))

    def snapshot():
        current = read_json(root / "manifest.json")
        transcripts = {}
        for name, record in current["stages"].items():
            if name.startswith("asr/") and artifacts_valid(root, record):
                transcripts[name] = read_json(root / f"{name}.json")
        corrections = read_json(root / "corrections.json") if (root / "corrections.json").exists() else []
        claims = read_json(root / "reviewed-claims.json") if (root / "reviewed-claims.json").exists() else read_json(root / "claims.json")
        return {"token": token, "manifest": current, "transcripts": transcripts, "claims": claims,
                "frames": read_json(root / "frames.json"), "corrections": corrections,
                "enhanced_video_available": has_enhanced_video()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def acceptable_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.acceptable_host():
                return self.reply(403, {"error": "Loopback host required"})
            path = unquote(urlsplit(self.path).path)
            if path == "/api/state":
                return self.reply(200, snapshot())
            allowed = {"/": Path(__file__).with_name("review.html"),
                       "/video": root / "preview.mp4" if (root / "preview.mp4").exists() else Path(manifest["source_path"])}
            if path == "/enhanced-video.mp4" and has_enhanced_video():
                allowed[path] = root / "enhanced-video.mp4"
            for variant in ("reference", "baseline", "enhanced"):
                allowed[f"/{variant}.wav"] = root / f"{variant}.wav"
            for frame in read_json(root / "frames.json"):
                allowed["/" + frame["path"]] = root / frame["path"]
            target = allowed.get(path)
            if target is None or not target.is_file():
                return self.reply(404, {"error": "Not found"})
            size = target.stat().st_size
            start, end = 0, size - 1
            range_header = self.headers.get("Range")
            if range_header:
                try:
                    if not range_header.startswith("bytes=") or "," in range_header:
                        raise ValueError()
                    left, right = range_header[6:].split("-")
                    if not left:
                        count = int(right)
                        if count <= 0:
                            raise ValueError()
                        start = max(0, size - count)
                    else:
                        start = int(left)
                        end = min(int(right), size - 1) if right else size - 1
                    if not 0 <= start <= end < size:
                        raise ValueError()
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(206 if range_header else 200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with target.open("rb") as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            origin = self.headers.get("Origin")
            valid_origins = (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}")
            if not self.acceptable_host() or (origin and origin not in valid_origins) or not hmac.compare_digest(self.headers.get("X-Review-Token", ""), token):
                return self.reply(403, {"error": "Invalid local review token/origin"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError("Body must be 1–1048576 bytes")
                body = json.loads(self.rfile.read(length))
                if urlsplit(self.path).path == "/api/corrections":
                    if set(body) != {"target", "text", "unclear"} or not isinstance(body["text"], str) or not isinstance(body["unclear"], bool):
                        raise ValueError("Expected target, text, unclear")
                    state = snapshot()
                    targets = {s["id"]: s["text"] for t in state["transcripts"].values() for s in t["segments"]}
                    if body["target"] not in targets:
                        raise ValueError("Unknown transcript target")
                    record = {**body, "original": targets[body["target"]], "reviewed_at": now(), "review_status": "user_reviewed"}
                    with lock:
                        corrections = read_json(root / "corrections.json") if (root / "corrections.json").exists() else []
                        write_json(root / "corrections.json", corrections + [record])
                elif urlsplit(self.path).path == "/api/claims":
                    # Validate a separate candidate; immutable machine claims are never overwritten.
                    with lock:
                        candidate = root / "claims.candidate.json"
                        try:
                            write_json(candidate, body)
                            validate_claims(root, candidate)
                            history = read_json(root / "claims-review-history.json") if (root / "claims-review-history.json").exists() else []
                            write_json(root / "claims-review-history.json", history + [{"reviewed_at": now(), "claims": body}])
                            write_json(root / "reviewed-claims.json", body)
                        finally:
                            candidate.unlink(missing_ok=True)
                else:
                    return self.reply(404, {"error": "Unknown endpoint"})
                self.reply(200, {"saved": True})
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception as exc:
                from jsonschema import ValidationError
                if isinstance(exc, ValidationError):
                    self.reply(400, {"error": exc.message})
                else:
                    self.reply(500, {"error": "Local storage error; inspect run files"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Local review server on port {server.server_port}; Ctrl-C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
