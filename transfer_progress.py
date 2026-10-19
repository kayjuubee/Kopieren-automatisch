"""Per-run remaining work and measured ETA, including optional verification."""
import time


class TransferProgress:
    def __init__(self, sizes, verify=False, deferred=0, callback=None):
        self.pending = dict(sizes)
        self.total_bytes = sum(self.pending.values())
        self.verify = verify
        self.deferred = deferred
        self.callback = callback
        self.started = time.monotonic()
        self.processed = 0
        self.current = None
        self.copied = self.checked = 0
        self.completed = 0
        self.last_report = float('-inf')

    def start(self, name, size):
        self.current = name
        self.total_bytes += size - self.pending.get(name, 0)
        self.pending[name] = size
        self.copied = self.checked = 0
        self.report(force=True)

    def advance(self, size, checking=False):
        self.processed += size
        if checking:
            self.checked += size
        else:
            self.copied += size
        self.report()

    def finish(self, name, delivered=False, deferred=False):
        self.total_bytes -= self.pending.pop(name, 0)
        self.completed += int(delivered)
        self.deferred += int(deferred)
        self.current = None
        self.copied = self.checked = 0
        self.report(force=True)

    def snapshot(self):
        total = self.total_bytes
        remaining_bytes = max(0, total - self.copied)
        work = remaining_bytes + (max(0, total - self.checked) if self.verify else 0)
        elapsed = max(0, time.monotonic() - self.started)
        eta = work * elapsed / self.processed if self.processed and elapsed >= 1 else None
        if not self.pending:
            eta = 0
        return {'remaining_files': len(self.pending), 'remaining_bytes': remaining_bytes,
                'eta_seconds': eta, 'completed': self.completed, 'deferred': self.deferred}

    def report(self, force=False):
        if not self.callback:
            return
        now = time.monotonic()
        if force or now - self.last_report >= 0.5:
            self.callback(self.snapshot())
            self.last_report = now


def format_remaining(value):
    size = value['remaining_bytes']
    amount = f'{size / 1073741824:.2f} GiB' if size >= 1073741824 else f'{size / 1048576:.1f} MiB'
    eta = value['eta_seconds']
    if eta is None:
        duration = 'Restzeit wird ermittelt'
    else:
        seconds = max(0, int(eta + 0.999))
        duration = f'ca. {seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
    text = f"Dieser Durchlauf: noch {value['remaining_files']} Dateien · {amount} · {duration}"
    if value['deferred']:
        text += f" · {value['deferred']} noch in Bearbeitung / zurückgestellt"
    return text
