"""Tray callbacks only enqueue messages; Tk is accessed on its own thread."""
from pathlib import Path
import pystray
from PIL import Image


def start_tray(messages):
    path = Path(__file__).parent / 'assets' / 'kayjuubee.png'
    with Image.open(path) as original:
        icon_image = original.convert('RGBA')
        icon_image.thumbnail((64, 64))
    icon = pystray.Icon('kayjuubee', icon_image, 'kayjuubee USB Transfer', menu=pystray.Menu(
        pystray.MenuItem('Programm öffnen', lambda *_: messages.put(('show', None)), default=True),
        pystray.MenuItem('Beenden', lambda *_: messages.put(('exit', None)))),
    )
    icon.run_detached()
    return icon
