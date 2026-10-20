# Jiu-Jitsu Technique Library — Codex Handoff

Created: October 20, 2026

## Start here: instructions for Codex

Use this document as the project brief. Start implementing the local video-processing proof of concept described below. Do not build the full application first. Inspect this checkout and any AGENTS.md instructions, then make a short implementation plan and proceed with reversible local work. Preserve existing files and the original video. Do not activate paid services or upload instructor footage to third-party AI services without the user's explicit authorization. Use a project-specific virtual environment; avoid global Python package changes. Explain any required system installation before performing it, and follow the execution environment's approval rules.

The user has an **M4 MacBook Air**. Inspect available RAM, macOS, disk space, Python, FFmpeg, and Apple Silicon support before selecting model size. Use free, local processing by default. Ask only for missing information that blocks progress; leave unknown instructor/date/location fields empty rather than inventing values.

First locate `IMG_6970.MOV` in the project or a user-specified input directory. If absent, ask the user for its local path. The prior chat attachment and its temporary cloud path are not guaranteed to exist on this Mac. Markdown is a brief for Codex, not an executable program.

## Goal and agreed MVP scope

Build a searchable library of jiu-jitsu techniques with videos uploaded by the user, including instruction from their own instructors. Internet sourcing is limited to **technique names, aliases, and taxonomy references**. Do not scrape, download, or ingest internet instructional videos for MVP.

Search and filter by position, technique name or alias, offense/defense/counter, action category, submission type, gi/no-gi, top/bottom perspective, instructor, recording date, and location. Support multiple values per instructional segment where appropriate.

The highest-value capability is extracting technical execution details and situational conditions from uploaded videos: when a technique is available, why it works, mistakes, opponent reactions, and follow-ups. A generic summary is insufficient.

## Current state and constraints

- This is a new project; no application, database, or processing pipeline has been implemented or validated in this conversation.
- Test input: `IMG_6970.MOV`. Duration, codecs, audio quality, contents, instructor, recording date, and location are not yet verified.
- An earlier JPEG attachment was unsuitable for the audio/video PoC.
- Earlier chat attempts failed because that session's execution environment was unavailable. This was not evidence of a corrupt MOV or a limitation of the user's Mac. No transcript or technique analysis was produced.
- Optimize for $0 incremental service spending during the PoC. Downloads and local compute still consume bandwidth, disk, and battery.
- Preserve originals; keep derived audio, transcripts, frames, and analysis separately. Private instructor footage stays local by default.

## Phase 1: local video-processing PoC

### A. Inspect and extract

1. Inspect the actual MOV with ffprobe. Record duration, codecs, sample rate, channels, rotation/orientation, and available recording metadata.
2. Store file hash and extraction settings for reproducibility. Treat embedded dates/location as candidates, not confirmed user metadata; distinguish recording time from upload/file modification time.
3. Extract audio using FFmpeg. Preserve an unfiltered reference track and original channel information. Listen to a short representative sample before choosing downmixing or channel selection.
4. Produce an ASR-compatible mono track if needed. Do not overwrite originals or claim resampling improves the source quality.
5. Extract timestamped frames sparingly for review; retain rotation and synchronization. Prefer clips or denser sampling around ambiguous movements rather than pretending isolated frames fully describe motion.

### B. Baseline transcription

Use **MLX Whisper** on Apple Silicon as the initial local ASR candidate. Verify current package instructions and compatible model identifiers before installing or coding. Open-source Whisper is an alternative if MLX is incompatible. Choose a model that fits available memory, run a short sample first, then process the full file.

Export raw model output, timestamped JSON, readable text, and SRT or VTT. Record model identifier, package versions, language settings, decoding options, timing granularity, elapsed time, and any glossary prompt. Do not assume word timestamps or speaker diarization are available without validating the chosen implementation. Speaker identity must not be inferred from ASR alone.

Gym audio can be quiet, reverberant, or covered by background speech. Mark unclear passages; watch for hallucinated words during silence. Keep an untouched baseline transcript. A technique glossary may help recognition but can also bias ambiguous speech; record its use and inspect technique names carefully.

### C. Compare modest audio enhancement

Create a separate candidate with conservative, reproducible local processing such as normalization and suitable filtering, selected after inspecting the audio. Avoid aggressive filtering that damages consonants. Transcribe using the same model/settings as the baseline so differences are interpretable.

Compare representative difficult passages against human listening. Report whether enhancement helps, harms, or makes no difference. Agreement between two transcripts is not proof of correctness. Never invent speech that remains inaudible. Speaker separation and trained speech enhancement are optional later experiments, not prerequisites.

### D. Extract structured teaching notes

Separate:

- **Spoken evidence:** what can be heard in the video, with transcript and timestamps.
- **Visual observation:** what is directly visible, including uncertainty from occlusion or camera angle.
- **Inference:** a proposed interpretation or situational recommendation, explicitly marked for review.

For each instructional segment capture candidate technique/position, start/end time, perspective, grips, starting conditions, opponent cues, ordered execution steps, essential details, mistakes, failure conditions, counters, and follow-ups. Every extracted claim must point to supporting evidence or be marked unsupported/inferred. Missing information stays unknown.

Do not assume local transcription also provides visual understanding or semantic extraction. If the Codex session can inspect frames, describe those observations with their limits. If a suitable local language/vision model is available and fits memory, benchmark it on a sample before committing. Otherwise produce the transcription, review assets, extraction schema, and clearly state what remains untested. Do not fabricate a completed visual analysis. Optional Google AI Studio/Gemini analysis requires user authorization to upload footage and a check of current eligible free models, quotas, and data-use terms.

### E. Review and assess feasibility

Create a lightweight local review page or equivalent practical review workflow showing the video, timestamped transcript, unclear spans, candidate tags, and extracted claims. Clicking a timestamp should seek playback. Support corrections without destroying the original machine output. Keep the page local; no hosting or account system is needed for this experiment.

Select several representative spans, including difficult audio, and ask the user to correct a reference transcript and assess missing/misinterpreted details. Report observed transcription errors, technique-name accuracy, timestamp usability, unsupported claims, and critical details missed. WER is optional and only meaningful with a human reference; never report invented accuracy percentages. Keep human-confirmed evidence separate from model confidence, which is not a calibrated reliability score.

## PoC deliverables

- Runnable local pipeline with a documented command accepting an input path; do not hard-code a user's home path.
- Project dependency/environment instructions and pinned or recorded working versions.
- Original metadata report and reproducibility manifest.
- Baseline and enhanced audio outputs, raw transcripts, timestamped JSON, and subtitles.
- Timestamped frames or review clips where useful.
- Structured segment/claim JSON with schema validation.
- Local review workflow and persisted human corrections.
- `POC_FINDINGS.md`: actual results, limitations, timing/memory observations, audio comparison, and next recommendation.
- Proposed ontology and SQL schema/migrations in draft form, with example records clearly labeled synthetic unless sourced from the actual video.

Keep large footage, derived media, credentials, and caches out of git. If git is used, commit source/configuration and small safe examples only. Make processing resumable, avoid re-running expensive stages unnecessarily, and cache by source hash plus processing settings.

## Proposed information architecture

This is a design starting point, not a finalized schema. Use stable IDs and controlled relationships rather than a flat pile of tags. A position is different from an action: X guard is a position; an entry into X guard is a technique. Chokes/strangles are a subtype of submission, not a mutually exclusive alternative to submission.

| Entity | Essential fields / purpose |
| --- | --- |
| Position | ID, preferred name, description, review status |
| Position alias | Position ID, alias, language, source ID |
| Position relationship | Subject, typed predicate, object; e.g. variant_of |
| Technique | ID, preferred name, description, review status |
| Technique alias | Technique ID, alias, language, source ID |
| Classification term | Controlled category and hierarchy; pass/sweep/escape/submission/takedown/transition, submission subtype |
| Technique classification | Technique ID, classification term ID |
| Technique-position relationship | Technique ID, position ID, role such as starts_from/ends_in; context when needed |
| Technique relationship | Subject technique, predicate such as variation_of/counters/follows_up_with, object, conditions/evidence |
| Source | URL or local reference, title, attribution, access date; provenance for imported names and relationships |
| Instructor | ID, display name; affiliation modeled separately if needed |
| Location | ID, venue/academy name, city, optional address |
| Video | ID, file reference, hash, title, recording date/time and precision, timezone if known, upload time, location ID, processing status |
| Video instructor | Many-to-many video/instructor links; explicit role if known |
| Instructional segment | Video ID, start/end seconds, summary, perspective, gi/no-gi, review status |
| Segment technique / position | Many-to-many links with role, evidence, and review status |
| Segment instructor | Explicit segment instructor link; inherits video context only when unambiguous |
| Transcript segment | Video ID, start/end, text, optional speaker label, processing run ID |
| Teaching claim | Segment ID, kind, content, ordered step index where applicable, evidence basis, review status |
| Claim evidence | Claim ID, time range, transcript segment/frame references, supporting excerpt |
| Processing run | Source hash, stage, model/tool/version, configuration, timestamps, status, output references |
| Review / correction | Target entity, original value, corrected value, reviewer, timestamp |

### Ontology rules

- A video may contain multiple techniques; one technique may have many videos and instructor-specific variations.
- Store instructor teaching claims against segments before promoting any information into canonical technique knowledge.
- Keep position, technique family, action, intent, and top/bottom perspective distinct. A segment may involve both attack and defense.
- Starting/ending positions and technique relationships may depend on gi/no-gi, grips, opponent posture, or other conditions; avoid unconditional links where evidence is conditional.
- Aliases are many-to-one naming links, while genuinely different variations remain distinct concepts. Merging duplicates should preserve references and provenance.
- Enforce valid segment boundaries and reference integrity. Validate taxonomy relationship types and prevent cycles in hierarchical broader/narrower links.
- Dates can be date-only or unknown; avoid fabricated midnight timestamps. Keep upload time separate.
- Store explicit review states such as machine_proposed, user_reviewed, instructor_verified, rejected. Do not label something instructor_verified without actual verification.
- For MVP, ontology ingestion is curated and reviewable. Capture sources and deduplicate before publishing new names. Completeness across all jiu-jitsu terminology is not a realistic acceptance criterion.

## Future application, after the PoC

Potential stack: mobile-friendly React/Next.js UI, Supabase/Postgres for relational data and authentication, private object storage for uploads, full-text plus alias search initially, and pgvector later for situational semantic search. Add a background worker when processing is hosted. Dedicated video delivery such as Cloudflare Stream and services such as TwelveLabs are optional later, not MVP requirements.

Example query: “Show my instructor's bottom half-guard techniques for when my opponent flattens me.” Results should respect structured filters, retrieve relevant segments, and show timestamp-backed conditions/details. Keep instructor-specific evidence visible and avoid unsupported synthesized coaching.

## Practical next actions for Codex

1. Inspect the local project and Mac capabilities; locate the input MOV.
2. Implement and run metadata/audio extraction plus a short baseline transcription.
3. Run full transcription and a controlled enhancement comparison.
4. Build review outputs and extract only claims supported by accessible evidence.
5. Draft the relational ontology schema and validate representative records.
6. Report actual findings and unresolved questions before expanding to the full app.

## Reference starting points

Verify current documentation before use; no free-tier availability or API price is guaranteed by this handoff.

- FFmpeg: https://ffmpeg.org/documentation.html
- MLX Whisper: https://github.com/ml-explore/mlx-examples/tree/main/whisper
- Open-source Whisper: https://github.com/openai/whisper
- Optional Gemini video analysis: https://ai.google.dev/gemini-api/docs/video-understanding
- Optional Gemini pricing/data-use overview: https://ai.google.dev/gemini-api/docs/pricing
- Optional Colab fallback: https://research.google.com/colaboratory/faq.html
- Future Supabase vector search: https://supabase.com/docs/guides/database/extensions/pgvector
