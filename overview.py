"""Summarize selected source files against the local delivery history."""
import os
import time
from pathlib import Path


def summarize(source, folders, thumbs, journal, age=10):
    source = Path(source).resolve()
    if not source.is_dir():
        raise OSError('Veranstaltung nicht verfügbar')
    result = {'total': 0, 'pending': 0, 'delivered': 0, 'recent': 0, 'volumes': {}, 'pending_files': []}
    def walk_error(error):
        raise error
    for name in folders:
        if Path(name).name != name or name in {'.', '..'}:
            raise ValueError('Ungültiger Ordner')
        folder = source / name
        if not folder.is_dir() or folder.is_symlink():
            continue
        for root, dirs, files in os.walk(folder, onerror=walk_error):
            root = Path(root)
            dirs[:] = [d for d in dirs if not (root / d).is_symlink() and not (name.lower() == 'prints' and d.lower() == 'thumbs' and not thumbs)]
            for name in files:
                path = root / name
                if path.is_symlink():
                    continue
                stat = path.stat()
                result['total'] += 1
                delivery = journal.delivery(path, stat)
                if delivery is None:
                    result['pending'] += 1
                    result['pending_files'].append(str(path.relative_to(source)))
                    if time.time() - stat.st_mtime < age:
                        result['recent'] += 1
                else:
                    result['delivered'] += 1
                    key = delivery['volume']
                    item = result['volumes'].setdefault(key, {'files': 0, 'bytes': 0, 'verified': 0, 'label': journal.volume_name(key)})
                    item['files'] += 1
                    item['bytes'] += stat.st_size
                    item['verified'] += delivery['verified']
    return result
