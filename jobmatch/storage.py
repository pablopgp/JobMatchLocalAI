import sqlite3

from jobmatch.config import home


def connect():
    db = sqlite3.connect(home() / "jobs.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY, received INTEGER NOT NULL, status TEXT NOT NULL,
      job_count INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
      context TEXT NOT NULL, first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      analysis TEXT, profile_hash TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS message_jobs (
      message_id TEXT REFERENCES messages(id), job_id TEXT REFERENCES jobs(id),
      PRIMARY KEY(message_id, job_id));
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, started TEXT DEFAULT CURRENT_TIMESTAMP,
      finished TEXT, status TEXT, messages INTEGER DEFAULT 0,
      analyzed INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
    """)
    return db
