import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copier import copy_new, VerificationError
from journal import Journal
from overview import summarize


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source, self.target = root / 'Event', root / 'USB'
        (self.source / 'Originals').mkdir(parents=True)
        self.target.mkdir()
        self.file = self.source / 'Originals' / 'a.jpg'
        self.file.write_bytes(b'original photo')
        self.journal = Journal(root / 'journal.sqlite3')
        self.addCleanup(self.journal.close)

    def test_verified_file_and_overview(self):
        phases = []
        self.journal.remember_volume('stick-one', 'Erster Stick')
        self.assertEqual(copy_new(self.source, self.target, ['Originals'], age=0, journal=self.journal,
                                  volume='stick-one', verify=True, phase=phases.append), 1)
        self.assertEqual((self.target / 'Event/Originals/a.jpg').read_bytes(), self.file.read_bytes())
        self.assertEqual(self.journal.delivery(self.file, self.file.stat()), {'volume': 'stick-one', 'verified': True})
        other = self.file.with_name('pending.jpg')
        other.write_bytes(b'pending')
        thumbs = self.source / 'Prints/thumbs/t.jpg'
        thumbs.parent.mkdir(parents=True)
        thumbs.write_bytes(b'thumbnail')
        result = summarize(self.source, ['Originals', 'Prints'], False, self.journal, age=0)
        self.assertEqual((result['total'], result['delivered'], result['pending']), (2, 1, 1))
        self.assertEqual(result['pending_files'], ['Originals/pending.jpg'])
        self.assertEqual(result['volumes']['stick-one']['verified'], 1)
        self.assertEqual(result['volumes']['stick-one']['label'], 'Erster Stick')
        self.assertTrue(any('prüfen' in phase for phase in phases))

    def test_corrupted_copy_not_published_or_recorded(self):
        def corrupt(_):
            temporary = next(self.target.rglob('.hotfolder-*'))
            temporary.write_bytes(b'corrupt content')
        with patch('copier.os.fsync', side_effect=corrupt):
            with self.assertRaises(VerificationError):
                copy_new(self.source, self.target, ['Originals'], age=0, journal=self.journal, verify=True)
        self.assertEqual(list((self.target / 'Event/Originals').iterdir()), [])
        self.assertFalse(self.journal.contains(self.file, self.file.stat()))

    def test_database_migrates_without_losing_existing_history(self):
        path = Path(self.tmp.name) / 'legacy.sqlite3'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE delivered (source TEXT, size INTEGER, modified INTEGER, volume TEXT, PRIMARY KEY(source,size,modified))')
        connection.execute('INSERT INTO delivered VALUES (?, ?, ?, ?)', (*Journal.key(self.file, self.file.stat()), 'old-stick'))
        connection.commit()
        connection.close()
        migrated = Journal(path)
        try:
            self.assertEqual(migrated.delivery(self.file, self.file.stat()), {'volume': 'old-stick', 'verified': False})
        finally:
            migrated.close()

    def test_source_modified_during_verification_is_retried(self):
        def phase(text):
            if 'prüfen' in text:
                self.file.write_bytes(b'new source data')
        self.assertEqual(copy_new(self.source, self.target, ['Originals'], age=0, journal=self.journal, verify=True, phase=phase), 0)
        self.assertFalse((self.target / 'Event/Originals/a.jpg').exists())
