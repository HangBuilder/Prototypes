# BJJ Coach — local video PoC

Turn a user-owned recording into reviewable evidence before building a technique
library. This is a Python CLI and a local review page, not the full application.
There is no hosted service, paid API, automatic coaching, or footage upload.

## Install

Python 3.11+ and `ffmpeg`/`ffprobe` on PATH are required. Use this existing checkout;
no worktree is needed. Commands below run from the `BJJ Coach` project directory.
On your Mac, start each Terminal session with:

```sh
cd "/Users/hangea/Documents/AI explorations/BJJ Coach/Prototypes/BJJ Coach"
```

All processing commands use `.venv/bin/python -m bjj_coach.cli` directly. This
avoids the `bjj-coach` launcher that failed to import the package on your Mac.
The current working directory must contain `bjj_coach/` and `.venv/`.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# Apple Silicon Mac (MLX); see the Linux alternative below.
python -m pip install -e '.[mac]'
```

Use Python 3.12 rather than Apple's Python 3.9. If the universal installer's
Python is not on PATH, create the environment with
`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv`.
If `.venv` already uses an older Python, deactivate it if active and rename it
before creating the new environment; installing Python does not upgrade an
existing virtual environment. Verify with `.venv/bin/python --version`.

On Linux/Intel, instead install `python -m pip install -e '.[cpu]'` for CPU/int8
faster-whisper. Top-level dependencies are pinned in `pyproject.toml`;
`requirements-linux-tested.txt` records the exact installed Linux environment,
not a cross-platform lockfile or a claim that MLX was tested here. To reproduce the
Linux environment, install that file first, then `python -m pip install -e .`.

Before processing on a Mac, inspect `uname -m`, `sw_vers`, `sysctl -n hw.memsize`,
`df -h .`, `python3 --version`, and `ffmpeg -version`. MLX requires macOS/arm64.
The default Mac workflow below uses `mlx-community/whisper-large-v3-mlx`, which
produced substantially better transcripts in your local trial. It downloads
several GB on first use and requires more memory than tiny/small; close other
memory-heavy apps and watch memory pressure. Smaller models remain optional. The M4 Mac's RAM and OS have
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

Keep originals outside Git, e.g. in ignored `data/`. To process a new video on
macOS, select it with the file picker and capture its output directory:

```sh
BJJ_VIDEO="$(osascript -e 'POSIX path of (choose file with prompt "Choose your new video")')"

BJJ_RUN="$(.venv/bin/python -m bjj_coach.cli prepare "$BJJ_VIDEO" --output runs)"

printf 'Run directory: %s\n' "$BJJ_RUN"
```

Stop if extraction reports an error. If `ffmpeg` is missing, install it with
`brew install ffmpeg` (requires Homebrew), verify `ffmpeg -version` and
`ffprobe -version`, then retry extraction. The file picker is Mac-only; on Linux
assign `BJJ_VIDEO="/path/to/video.mov"` before running the preparation command.

The command prints a run directory named after the source SHA-256 fingerprint.
`HASH` is a placeholder for that generated folder name, not text to type literally.
`BJJ_RUN` captures the real path and stays set only in the current Terminal session.
For another video, repeat the file picker and preparation commands above.

If you open a new Terminal, return to the project folder, run `ls -d runs/*/`, and
assign the desired full path (use no `$` on the left side):

```sh
# Example from the first recording; choose your new recording's path as needed.
BJJ_RUN="runs/2aaed35d39a70449f128110468625abc6eae91598938b344c4b6192f0df3fa8b"
```

Always quote `"$BJJ_RUN"` when passing it to a command; paths may contain spaces.
 `metadata.json` retains the complete ffprobe report
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

Transcribe the **entire video** on your Apple Silicon Mac:

```sh
.venv/bin/python -m bjj_coach.cli transcribe "$BJJ_RUN" \
  --backend mlx \
  --model mlx-community/whisper-large-v3-mlx \
  --language en
```

No `--sample-seconds` option is needed for full-video processing. For an optional
short trial on a longer recording, add `--sample-seconds 30`.

Linux CPU alternative (smaller model):

```sh
.venv/bin/python -m bjj_coach.cli transcribe "$BJJ_RUN" \
  --backend faster-whisper --model tiny --language en
```

Language defaults to English; use `--language` if needed. No word timings or
speaker identity are claimed. Temperature is zero and previous-text conditioning
is disabled; settings and optional `--prompt` glossary are recorded. Keep the
initial baseline free of glossary bias. Sample runs cover the beginning of the
recording; the review page can inspect difficult spans throughout a full run.

A different settings hash creates a separate ASR run instead of overwriting
an earlier one. Outputs: `.raw.json`, normalized timestamped `.json`, `.txt`, and
`.srt`. Silence and low-score flags prompt review; they are not accuracy scores.

```sh
# Optional candidate; evaluate before accepting the filter for your gym audio.
.venv/bin/python -m bjj_coach.cli enhance "$BJJ_RUN"
.venv/bin/python -m bjj_coach.cli transcribe "$BJJ_RUN" \
  --backend mlx \
  --model mlx-community/whisper-large-v3-mlx \
  --language en \
  --variant enhanced
# Use the SAME backend/model/revision/language/prompt/sample options as baseline.
```

The candidate uses `highpass=f=80,loudnorm=I=-20:TP=-2:LRA=11`. It is conservative
but may still hurt speech; no benefit has been established. Compare difficult
passages by human listening. Two matching outputs are not proof of correctness.
Do not invent words that remain inaudible.

## Video with enhanced audio

Export a separate browser-compatible MP4 with the enhanced audio track:

```sh
.venv/bin/python -m bjj_coach.cli preview "$BJJ_RUN" --audio enhanced
```

This creates `enhanced-video.mp4` in the run directory and generates enhanced audio
if needed. The original stays unchanged. The export uses H.264 video and AAC audio;
its enhanced mono track is aligned to the same timeline as transcript timestamps.
If the audio ends early, silence is padded so the video is not cut short. Repeated
exports reuse valid output unless source/audio/settings change.

Start or restart the review server below, then refresh your browser. Use the
**Video audio** dropdown to switch between original and enhanced playback without
losing your position. **Download video with enhanced audio** saves the MP4 to your
Mac. If no export exists, the enhanced option is disabled.

## Review and correct

```sh
# Optional if the original MOV codec will not play in your browser:
.venv/bin/python -m bjj_coach.cli preview "$BJJ_RUN"
.venv/bin/python -m bjj_coach.cli review "$BJJ_RUN" --port 8765
```

Open `http://127.0.0.1:8765` in your Mac's browser once the server starts.
Keep that Terminal running; press Control-C to stop it before running another
processing command in the same Terminal. The server binds only
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
.venv/bin/python -m bjj_coach.cli validate "$BJJ_RUN"
.venv/bin/python -m unittest discover -s tests -v
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

## Compare a technical detail across two class videos

The class review page implements **technique → technical detail → linked moments**.
This is a manual two-video experiment, not automatic cross-video matching.
Existing single-video review, machine transcripts, and corrections stay intact.

Start from the project directory with the review server stopped (Control-C).
Select the two original videos in class teaching order. Preparation reuses valid
outputs for videos already processed:

```sh
BJJ_VIDEO_1="$(osascript -e 'POSIX path of (choose file with prompt "Choose the FIRST video from the class")')"
BJJ_RUN_1="$(.venv/bin/python -m bjj_coach.cli prepare "$BJJ_VIDEO_1" --output runs)"

BJJ_VIDEO_2="$(osascript -e 'POSIX path of (choose file with prompt "Choose the SECOND video from the same class")')"
BJJ_RUN_2="$(.venv/bin/python -m bjj_coach.cli prepare "$BJJ_VIDEO_2" --output runs)"
```

Stop if either preparation fails. If these recordings do not already have full
transcripts, transcribe each using the earlier large-v3 command. For example:

```sh
.venv/bin/python -m bjj_coach.cli transcribe "$BJJ_RUN_1" --backend mlx --model mlx-community/whisper-large-v3-mlx --language en
.venv/bin/python -m bjj_coach.cli transcribe "$BJJ_RUN_2" --backend mlx --model mlx-community/whisper-large-v3-mlx --language en
```

Create compatible original-audio previews, then register the class once:

```sh
.venv/bin/python -m bjj_coach.cli preview "$BJJ_RUN_1"
.venv/bin/python -m bjj_coach.cli preview "$BJJ_RUN_2"

.venv/bin/python -m bjj_coach.cli class-create classes/two-video-trial.json \
  --title "Two-video class trial" --runs "$BJJ_RUN_1" "$BJJ_RUN_2"

.venv/bin/python -m bjj_coach.cli class-review classes/two-video-trial.json --port 8765
```

Open `http://127.0.0.1:8765` and refresh if the single-video page is cached.
The class file must not already exist when creating it. To resume a saved trial,
run only `class-review`; no need to select or reprocess the videos again.

1. Add a technique, for example **Guard pull**.
2. Add a technical detail, for example **Control hands before bringing legs in**.
   Enter any conditions separately rather than treating a conditional detail as universal.
3. Choose video 1 and the desired transcript run. Click **Use this span** to copy
   its timestamps, stable transcript reference, and spoken quote into the link form.
4. Choose a teaching role (initial explanation, correction, repetition, variation,
   exception, or follow-up), add notes, and save the linked moment.
5. Select video 2, find the relevant span, and attach it to the **same detail**.
6. The right panel shows all matching moments in class order. **Play this detail**
   starts one second before the span and pauses at its end. Compare the instruction
   and use **Edit link** or **Remove link** to correct mistaken associations.

You can select sparse frames for explicitly visual observations or mark an
interpretation as **Inference · needs review** with an explanatory note. The
validator checks bounds, registered videos, references, and quoted text, including
saved transcript corrections. It cannot determine whether two spans teach the same
concept or whether an observation is true. All associations are labeled user-linked,
not instructor-verified. Existing enhanced-video exports are available as audio
choices in both the source player and matching moments.

Class annotations and previous saved versions live in ignored `classes/*.json`.
Back up that folder along with `runs/`; these are local user data, not committed
examples. The collection references original run directories rather than copying
media, so keep those directories available. Selecting the same source twice is
rejected. Class order is the order passed to `--runs`; ordering does not imply a
technical follow-up relationship. This first workflow does not automatically infer
technique transitions or match technical details across recordings.

For the first trial, link two or three details and evaluate: did both timestamps
land on relevant instruction, did the second explanation add a correction or
condition, and did any proposed association turn out to be wrong? Actual outcomes
require your two local recordings; synthetic integration tests do not establish
semantic accuracy.

## Status and limits

See [POC_FINDINGS.md](POC_FINDINGS.md) for the initial cloud validation results and
blockers. You subsequently ran transcription on your Mac and reported substantially
better results with large-v3. No transcript accuracy or visual technique analysis
has been independently validated here. The cloud attachment exceeds the available 32 MiB transfer limit;
the Mac can process the original directly using its local path. Cloud model
retrieval was separately blocked by a network proxy 403 for Hugging Face.

Draft SQL lives in `schemas/001_draft.sql` and is not applied automatically. Search,
curated taxonomy ingestion, canonical knowledge, and a full app come after this
experiment demonstrates useful evidence extraction.
