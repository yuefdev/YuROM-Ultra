-- SPDX-License-Identifier: GPL-3.0-or-later
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS installations (
  id TEXT PRIMARY KEY,
  first_day TEXT NOT NULL,
  last_day TEXT NOT NULL,
  model TEXT NOT NULL,
  build TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
  installation TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  model TEXT NOT NULL,
  build TEXT NOT NULL,
  oc_mode TEXT NOT NULL,
  PRIMARY KEY (installation, day)
);
CREATE TABLE IF NOT EXISTS issues (
  installation TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  model TEXT NOT NULL,
  build TEXT NOT NULL,
  category TEXT NOT NULL,
  signature TEXT NOT NULL,
  component TEXT NOT NULL,
  exception TEXT NOT NULL,
  frames TEXT NOT NULL,
  PRIMARY KEY (installation, day, category, signature)
);
CREATE INDEX IF NOT EXISTS activity_day ON activity(day);
CREATE INDEX IF NOT EXISTS issues_day ON issues(day);
CREATE INDEX IF NOT EXISTS installation_last_day ON installations(last_day);
