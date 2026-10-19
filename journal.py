"""Local, durable record of files successfully delivered, across USB sticks."""
import sqlite3
from pathlib import Path


class Journal:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS delivered (source TEXT, size INTEGER, modified INTEGER, volume TEXT, PRIMARY KEY(source, size, modified))')
        self.db.execute('CREATE TABLE IF NOT EXISTS volumes (identity TEXT PRIMARY KEY, label TEXT NOT NULL)')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(delivered)')}
        if 'verified' not in columns:
            self.db.execute('ALTER TABLE delivered ADD COLUMN verified INTEGER NOT NULL DEFAULT 0')
        self.db.commit()

    @staticmethod
    def key(path, stat):
        return str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns

    def contains(self, path, stat):
        return self.db.execute('SELECT 1 FROM delivered WHERE source=? AND size=? AND modified=?', self.key(path, stat)).fetchone() is not None

    def delivery(self, path, stat):
        row = self.db.execute('SELECT volume, verified FROM delivered WHERE source=? AND size=? AND modified=?', self.key(path, stat)).fetchone()
        return {'volume': row[0], 'verified': bool(row[1])} if row else None

    def record(self, path, stat, volume, verified=False):
        self.db.execute('INSERT OR REPLACE INTO delivered (source, size, modified, volume, verified) VALUES (?, ?, ?, ?, ?)', (*self.key(path, stat), volume, int(verified)))
        self.db.commit()

    def remember_volume(self, identity, label):
        self.db.execute('INSERT OR REPLACE INTO volumes VALUES (?, ?)', (identity, label))
        self.db.commit()

    def volume_name(self, identity):
        row = self.db.execute('SELECT label FROM volumes WHERE identity=?', (identity,)).fetchone()
        return row[0] if row else identity

    def close(self):
        self.db.close()
