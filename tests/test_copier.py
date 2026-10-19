import tempfile
import unittest
from pathlib import Path
from copier import copy_new, events

class CopyTests(unittest.TestCase):
    def test_copy_filters_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root/'Event', root/'USB'
            target.mkdir()
            for name in ['Originals/a.jpg', 'Prints/b.jpg', 'Prints/thumbs/t.jpg', 'Videos/v.mp4']:
                path = source/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'photo')
            self.assertEqual(copy_new(source, target, ['Originals', 'Prints'], age=0), 2)
            self.assertFalse((target/'Event/Prints/thumbs').exists())
            self.assertFalse((target/'Event/Videos').exists())
            (source/'Originals/a.jpg').write_bytes(b'changed')
            self.assertEqual(copy_new(source, target, ['Originals', 'Prints'], age=0), 0)
            self.assertEqual((target/'Event/Originals/a.jpg').read_bytes(), b'photo')
            self.assertEqual(copy_new(source, target, ['Prints', 'Videos'], thumbs=True, age=0), 2)

    def test_recent_files_and_invalid_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root/'Event', root/'USB'
            (source/'Originals').mkdir(parents=True)
            target.mkdir()
            (source/'Originals/a.jpg').write_bytes(b'photo')
            self.assertEqual(copy_new(source, target, ['Originals']), 0)
            with self.assertRaises(ValueError):
                copy_new(source, source, ['Originals'])
            with self.assertRaises(ValueError):
                copy_new(source, target, ['..'])
            with self.assertRaises(OSError):
                copy_new(source, root/'absent', ['Originals'])
            self.assertEqual(set(events(root)), {source, target})
