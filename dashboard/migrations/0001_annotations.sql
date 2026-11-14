CREATE TABLE IF NOT EXISTS annotations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  transcript_hash TEXT NOT NULL,
  quote TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL,
  reviewer TEXT NOT NULL DEFAULT 'Anonymous',
  outcome TEXT CHECK(outcome IN ('concealed','reported','unresolved') OR outcome IS NULL),
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1))
);
CREATE INDEX IF NOT EXISTS annotations_run ON annotations(run_id, transcript_hash, updated_at);
CREATE TABLE IF NOT EXISTS annotation_history (
  id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  PRIMARY KEY (id, revision)
);
