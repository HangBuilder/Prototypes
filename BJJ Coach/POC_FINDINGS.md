# PoC findings — October 20, 2026

## Implemented and exercised

The empty local BJJ Coach repository now contains a CLI, optional local ASR
adapters (MLX and faster-whisper), evidence schema/validator, loopback review page,
correction storage, and draft relational ontology. There is no full application.

Current host: Linux x86_64, Python 3.12.14, FFmpeg/ffprobe 7.1.5. About 33 GiB RAM
and 30 GiB disk were available before dependencies/model testing. This is not the
user's M4 MacBook Air; macOS, RAM, Apple Silicon/MLX performance remain untested.
Project-specific virtual environment; no global/system installs were performed.
Official MLX README was consulted for the transcribe API and default model ID;
MLX 0.4.3 and faster-whisper 1.2.1 are pinned optional dependencies. Linux package
installation succeeded; exact installed packages are recorded separately.

A generated 3-second color-pattern/sine-wave MOV (not user footage) exercised the
CLI: metadata, stereo 48 kHz reference, mono 16 kHz baseline, three timestamped
frames, a separate enhancement, and H.264/AAC preview. Observed initial stage times:
reference ~0.04 s, mono ~0.05 s, frames ~0.15 s, enhancement ~0.08 s, preview ~0.14 s.
These tiny-fixture timings do not predict real-video performance. Peak pipeline
memory was not measured. No speech was present in that fixture.

All 11 tests passed in the final suite run (~1.1 seconds). Dependency consistency
(`pip check`) also passed. The suite covers original preservation, source channel/rate retention,
mono output, frame timestamps, stage reuse, corrupt-output repair, independent
repeatable enhancement, valid/invalid evidence, subtitle rounding, draft SQL
constraints, a synthetic positive audio offset with silence padding, actual HTTP serving/range seeking, write-token rejection, persisted
corrections, and separate reviewed claims/history. Adapter/export tests, where
present, use synthetic responses and do not validate inference or speech accuracy.

## Blocked or untested

- IMG_6970.MOV could not be transferred: the available attachment-download tool has
  a 32 MiB maximum. No footage was inspected or uploaded to another AI service.
- Real CPU model loading was attempted with faster-whisper `tiny` and a 2-second
  fixture sample. Hugging Face retrieval failed with proxy `403 Forbidden`, before
  inference. Failed stage/error is recorded in the ignored run manifest. TLS was
  not disabled and no alternate route was used to bypass the restriction.
- Real ASR inference, full-file transcription, Mac MLX execution, word accuracy,
  instructor identity, technique-name accuracy, difficult gym audio, orientation
  on actual footage, nonzero audio offsets on real recordings, and human listening remain untested.
- Enhancement quality is **unknown**. No human reference transcript exists, so
  WER and accuracy percentages cannot be reported.
- Teaching claims are empty until evidence can be inspected. No semantic or visual
  model was installed. No situational recommendation is represented as fact.
- The review HTTP API is integration-tested; visual browser interaction has not
  been manually inspected in this environment. It is a local single-user prototype.

## Next experiment

Run `prepare` on the original's local Mac path. Listen to the untouched reference,
confirm channel choice and sync, then transcribe a 30-second MLX tiny sample.
Only after that succeeds, transcribe the full baseline and enhanced candidate
with identical settings. Correct several easy, difficult, and silent spans in
the review page; measure technique-name errors, timestamp usefulness, and missed
critical details. Fill evidence-backed segment notes and decide whether a larger
local model is justified before building search or a hosted app.

For cloud inference, environment Internet access must allow the public model
host (`huggingface.co`) and any artifact-host redirects returned by its download
service. No credentials are required for the selected public model. No network
configuration, publication, GitHub push, or paid service activation was performed.
