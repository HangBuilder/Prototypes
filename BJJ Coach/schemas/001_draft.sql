-- DRAFT: SQLite prototype, not an applied production migration.
-- Foreign keys must be enabled on every connection. Unknown metadata stays NULL.
PRAGMA foreign_keys = ON;
CREATE TABLE source (
 id TEXT PRIMARY KEY, reference TEXT NOT NULL, title TEXT, attribution TEXT, accessed_on TEXT
);
CREATE TABLE position (
 id TEXT PRIMARY KEY, preferred_name TEXT NOT NULL,
 review_status TEXT NOT NULL DEFAULT 'machine_proposed' CHECK(review_status IN ('machine_proposed','user_reviewed','instructor_verified','rejected'))
);
CREATE TABLE technique (
 id TEXT PRIMARY KEY, preferred_name TEXT NOT NULL, description TEXT,
 review_status TEXT NOT NULL DEFAULT 'machine_proposed' CHECK(review_status IN ('machine_proposed','user_reviewed','instructor_verified','rejected'))
);
CREATE TABLE position_alias (
 position_id TEXT NOT NULL REFERENCES position(id), alias TEXT NOT NULL, language TEXT,
 source_id TEXT REFERENCES source(id), PRIMARY KEY(position_id,alias)
);
CREATE TABLE technique_alias (
 technique_id TEXT NOT NULL REFERENCES technique(id), alias TEXT NOT NULL, language TEXT,
 source_id TEXT REFERENCES source(id), PRIMARY KEY(technique_id,alias)
);
CREATE TABLE position_relationship (
 subject_id TEXT NOT NULL REFERENCES position(id), predicate TEXT NOT NULL CHECK(predicate IN ('variant_of','broader_than','related_to')),
 object_id TEXT NOT NULL REFERENCES position(id), source_id TEXT REFERENCES source(id),
 CHECK(subject_id <> object_id), PRIMARY KEY(subject_id,predicate,object_id)
);
CREATE TABLE classification_term (
 id TEXT PRIMARY KEY, name TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('action','submission_subtype')),
 parent_id TEXT REFERENCES classification_term(id), CHECK(id <> parent_id)
);
CREATE TRIGGER classification_no_insert_cycle BEFORE INSERT ON classification_term
WHEN NEW.parent_id IS NOT NULL BEGIN
 SELECT RAISE(ABORT,'classification cycle') WHERE EXISTS (
  WITH RECURSIVE ancestors(id) AS (
   SELECT NEW.parent_id UNION SELECT parent_id FROM classification_term JOIN ancestors ON classification_term.id=ancestors.id WHERE parent_id IS NOT NULL
  ) SELECT 1 FROM ancestors WHERE id=NEW.id
 );
END;
CREATE TRIGGER classification_no_update_cycle BEFORE UPDATE OF parent_id ON classification_term
WHEN NEW.parent_id IS NOT NULL BEGIN
 SELECT RAISE(ABORT,'classification cycle') WHERE EXISTS (
  WITH RECURSIVE ancestors(id) AS (
   SELECT NEW.parent_id UNION SELECT parent_id FROM classification_term JOIN ancestors ON classification_term.id=ancestors.id WHERE parent_id IS NOT NULL
  ) SELECT 1 FROM ancestors WHERE id=NEW.id
 );
END;
CREATE TRIGGER position_no_cycle BEFORE INSERT ON position_relationship
WHEN NEW.predicate IN ('variant_of','broader_than') BEGIN
 SELECT RAISE(ABORT,'position hierarchy cycle') WHERE EXISTS (
  WITH RECURSIVE reachable(id) AS (
   SELECT NEW.object_id UNION SELECT object_id FROM position_relationship JOIN reachable ON subject_id=reachable.id WHERE predicate=NEW.predicate
  ) SELECT 1 FROM reachable WHERE id=NEW.subject_id
 );
END;
-- Relationships are replaced with delete+insert to re-run cycle validation.
CREATE TRIGGER position_relationship_no_update BEFORE UPDATE ON position_relationship BEGIN
 SELECT RAISE(ABORT,'replace relationships using delete and insert');
END;
CREATE TABLE technique_classification (
 technique_id TEXT NOT NULL REFERENCES technique(id), term_id TEXT NOT NULL REFERENCES classification_term(id), PRIMARY KEY(technique_id,term_id)
);
CREATE TABLE technique_position (
 technique_id TEXT NOT NULL REFERENCES technique(id), position_id TEXT NOT NULL REFERENCES position(id),
 role TEXT NOT NULL CHECK(role IN ('starts_from','ends_in')), conditions TEXT, source_id TEXT REFERENCES source(id),
 PRIMARY KEY(technique_id,position_id,role)
);
CREATE TABLE technique_relationship (
 subject_id TEXT NOT NULL REFERENCES technique(id), predicate TEXT NOT NULL CHECK(predicate IN ('variation_of','counters','follows_up_with')),
 object_id TEXT NOT NULL REFERENCES technique(id), conditions TEXT, source_id TEXT REFERENCES source(id),
 CHECK(subject_id <> object_id), PRIMARY KEY(subject_id,predicate,object_id)
);
CREATE TABLE instructor (id TEXT PRIMARY KEY, display_name TEXT NOT NULL);
CREATE TABLE location (id TEXT PRIMARY KEY, venue TEXT, city TEXT, address TEXT);
CREATE TABLE video (
 id TEXT PRIMARY KEY, file_reference TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE CHECK(length(sha256)=64),
 title TEXT, duration REAL NOT NULL CHECK(duration>0),
 recording_time TEXT, recording_precision TEXT CHECK(recording_precision IN ('date','datetime')), recording_timezone TEXT,
 uploaded_at TEXT NOT NULL, location_id TEXT REFERENCES location(id), processing_status TEXT NOT NULL
);
CREATE TABLE video_instructor (
 video_id TEXT NOT NULL REFERENCES video(id), instructor_id TEXT NOT NULL REFERENCES instructor(id), role TEXT,
 PRIMARY KEY(video_id,instructor_id)
);
CREATE TABLE processing_run (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES video(id), source_sha256 TEXT NOT NULL,
 stage TEXT NOT NULL, tool TEXT NOT NULL, version TEXT, model TEXT, configuration_json TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL CHECK(status IN ('running','complete','failed')), outputs_json TEXT
);
CREATE TABLE instructional_segment (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES video(id), start REAL NOT NULL CHECK(start>=0),
 end REAL NOT NULL CHECK(end>start), summary TEXT, attire TEXT NOT NULL DEFAULT 'unknown' CHECK(attire IN ('gi','no_gi','unknown')),
 review_status TEXT NOT NULL DEFAULT 'machine_proposed' CHECK(review_status IN ('machine_proposed','user_reviewed','instructor_verified','rejected'))
);
CREATE TRIGGER segment_duration_insert BEFORE INSERT ON instructional_segment BEGIN
 SELECT RAISE(ABORT,'segment exceeds video duration') WHERE NEW.end > (SELECT duration FROM video WHERE id=NEW.video_id);
END;
CREATE TRIGGER segment_duration_update BEFORE UPDATE ON instructional_segment BEGIN
 SELECT RAISE(ABORT,'segment exceeds video duration') WHERE NEW.end > (SELECT duration FROM video WHERE id=NEW.video_id);
END;
CREATE TABLE segment_perspective (
 segment_id TEXT NOT NULL REFERENCES instructional_segment(id), value TEXT NOT NULL CHECK(value IN ('top','bottom','standing','unknown')), PRIMARY KEY(segment_id,value)
);
CREATE TABLE segment_intent (
 segment_id TEXT NOT NULL REFERENCES instructional_segment(id), value TEXT NOT NULL CHECK(value IN ('offense','defense','counter','unknown')), PRIMARY KEY(segment_id,value)
);
CREATE TABLE segment_technique (
 segment_id TEXT NOT NULL REFERENCES instructional_segment(id), technique_id TEXT NOT NULL REFERENCES technique(id), role TEXT,
 evidence_json TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'machine_proposed', PRIMARY KEY(segment_id,technique_id)
);
CREATE TABLE segment_position (
 segment_id TEXT NOT NULL REFERENCES instructional_segment(id), position_id TEXT NOT NULL REFERENCES position(id), role TEXT,
 evidence_json TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'machine_proposed', PRIMARY KEY(segment_id,position_id)
);
CREATE TABLE segment_instructor (
 segment_id TEXT NOT NULL REFERENCES instructional_segment(id), instructor_id TEXT NOT NULL REFERENCES instructor(id), PRIMARY KEY(segment_id,instructor_id)
);
CREATE TABLE transcript_segment (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES video(id), run_id TEXT NOT NULL REFERENCES processing_run(id),
 start REAL NOT NULL CHECK(start>=0), end REAL NOT NULL CHECK(end>start), text TEXT NOT NULL, speaker_label TEXT
);
CREATE TABLE teaching_claim (
 id TEXT PRIMARY KEY, segment_id TEXT NOT NULL REFERENCES instructional_segment(id),
 kind TEXT NOT NULL CHECK(kind IN ('grip','starting_condition','opponent_cue','execution_step','essential_detail','mistake','failure_condition','counter','follow_up')),
 content TEXT NOT NULL, step_index INTEGER CHECK(step_index>0),
 basis TEXT NOT NULL CHECK(basis IN ('spoken','visual','inferred','unsupported')),
 review_status TEXT NOT NULL DEFAULT 'machine_proposed' CHECK(review_status IN ('machine_proposed','user_reviewed','instructor_verified','rejected'))
);
CREATE TABLE claim_evidence (
 id TEXT PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES teaching_claim(id),
 basis TEXT NOT NULL CHECK(basis IN ('spoken','visual')), start REAL NOT NULL CHECK(start>=0), end REAL NOT NULL CHECK(end>=start),
 transcript_segment_id TEXT REFERENCES transcript_segment(id), frame_reference TEXT, excerpt TEXT NOT NULL,
 CHECK((basis='spoken' AND transcript_segment_id IS NOT NULL) OR (basis='visual' AND frame_reference IS NOT NULL))
);
CREATE TABLE review_correction (
 id TEXT PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL, original_json TEXT NOT NULL,
 corrected_json TEXT NOT NULL, reviewer TEXT, reviewed_at TEXT NOT NULL
);
CREATE INDEX transcript_video_time ON transcript_segment(video_id,start);
CREATE INDEX segment_video_time ON instructional_segment(video_id,start);
CREATE INDEX technique_alias_search ON technique_alias(alias COLLATE NOCASE);
CREATE INDEX position_alias_search ON position_alias(alias COLLATE NOCASE);
-- Evidence alignment, target polymorphism, entity ID immutability, recording date precision,
-- same-video references, review authorization, and taxonomy import deduplication need application
-- validation before production. This schema is a design artifact, not a claim of production readiness.
