"""Noninteractive smoke test for the packaged application; no USB writes."""
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk

from copier import copy_new
from journal import Journal


def run(report_path):
    report = {'platform': os.name, 'checks': [], 'hardware_test': 'not_run'}
    window = tk.Tk()
    window.withdraw()
    try:
        image = tk.PhotoImage(master=window, file=Path(__file__).parent / 'assets/kayjuubee.png')
        assert image.width() > 0 and image.height() > 0
        report['checks'].append('packaged_logo_and_tk')
    finally:
        window.destroy()
    from tray import start_tray  # verify bundled Pillow, pystray and platform backend
    assert callable(start_tray)
    report['checks'].append('tray_backend_import')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, target = root / 'Event', root / 'Target'
        (source / 'Originals').mkdir(parents=True)
        target.mkdir()
        original = source / 'Originals/photo.bin'
        original.write_bytes(b'kayjuubee smoke test')
        journal = Journal(root / 'history.sqlite3')
        try:
            assert copy_new(source, target, ['Originals'], age=0, verify=True, journal=journal, volume='test') == 1
            assert (target / 'Event/Originals/photo.bin').read_bytes() == original.read_bytes()
            assert journal.delivery(original, original.stat())['verified']
            assert copy_new(source, target, ['Originals'], age=0, journal=journal) == 0
        finally:
            journal.close()
    report['checks'].append('copy_verify_history_repeat')
    if os.name == 'nt':
        from startup import process_names
        assert process_names()
        report['checks'].append('windows_process_enumeration')
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
