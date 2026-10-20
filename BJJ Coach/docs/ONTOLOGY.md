# Draft ontology

This PoC stores video-specific evidence before any canonical coaching knowledge.
`schemas/001_draft.sql` is an executable SQLite design draft, not a hosted database.

Positions describe configurations (half guard, X guard). Techniques describe actions
(an entry, pass, sweep, escape, submission, takedown, or transition). Submission
subtypes descend from submission; choke/strangle is not a competing action category.
Aliases name one concept; variations have their own stable IDs and relationships.
Intent (offense/defense/counter), perspective, and attire are independent fields and
can have multiple values where appropriate. Starting/ending positions and follow-ups
need conditions, provenance, and review. Hierarchies must remain acyclic.

No taxonomy has been fetched, and no example in this repository is extracted from
IMG_6970.MOV. Tests use explicitly synthetic records only. A later curated importer
may use online names/aliases and taxonomy sources; instructional video ingestion is
outside scope. Do not automatically promote machine claims to canonical technique facts.

The processing JSON schema is `bjj_coach/claims.schema.json`. The CLI additionally
validates time ranges, source identity, reference existence, quoted spoken excerpts,
frame timestamps, unique IDs, and evidence basis. It cannot verify that a paraphrase
is entailed by a quote or that a visual claim is correct. `instructor_verified`
requires an actual instructor review; selecting a string is not that verification.
The local page is a single-user experiment with no identity or authorization system.

For each segment, fill `candidate_techniques`, `candidate_positions`, `perspectives`,
`intents`, `attire`, and `claims`. Keep unknown arrays empty, attire `unknown`, and
instructor/date/location null in the manifest. For a direct claim use `spoken` or
`visual` and supply evidence. Use `inferred` or `unsupported` explicitly otherwise.
Execution steps require a positive `step_index`. No automatic semantic/visual model
is included; this deliberate review boundary prevents fabricated teaching notes.

SQL limitations are called out at the bottom of the draft. Before production, add
cross-video evidence constraints, immutable identity rules, review authorization,
and robust date precision validation. Use PostgreSQL migrations only after the PoC
establishes usable transcription and evidence review.

## Class-detail experiment

`class-create` groups existing run directories in teaching order. `class-review`
adds stable technique and technical-detail identities, plus occurrences referencing
a video hash, start/end, spoken or visual evidence (or explicit inference), and a
teaching role. One detail can link to multiple techniques in the storage format;
the first UI creates a detail under one selected technique. Matching is manual.
Spoken quotes can refer to original or saved corrected transcript versions.
Class changes preserve prior document versions separately.

Class order is distinct from a conditional technical transition. Transitions,
series spanning classes, automatic suggestions, and global technique deduplication
remain future work. User-linked occurrences are proposals, not instructor verification.
