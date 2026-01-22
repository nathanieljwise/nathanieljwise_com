import sqlite3
from pathlib import Path

DB_PATH = Path("/var/www/html/nathanieljwise/shortener/shortener.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            target TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            FOREIGN KEY(link_id) REFERENCES links(id)
        );
        """)
