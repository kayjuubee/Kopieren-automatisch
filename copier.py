import errno
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from transfer_progress import TransferProgress


def events(parent):
    return sorted((p for p in Path(parent).iterdir() if p.is_dir()), key=lambda p: (p.stat().st_ctime_ns, p.name), reverse=True)


class DiskFull(OSError):
    pass


class VerificationError(OSError):
    pass


class CopyCancelled(Exception):
    pass


def copy_new(source, target, folders, thumbs=False, age=10, *,
             journal=None, volume='', rate=16, progress=None, valid_target=None,
             stop=None, verify=False, phase=None, overall=None, full_speed=False, ignore_history=False, session_delivered=None):
    if not full_speed and not 1 <= rate <= 64:
        raise ValueError('Geschwindigkeit muss zwischen 1 und 64 MiB/s liegen')

    def check_target():
        if stop is not None and stop.is_set():
            raise CopyCancelled('Kopiervorgang beendet')
        if valid_target and not valid_target():
            raise OSError('USB-Stick wurde entfernt oder ersetzt')

    def throttle(size):
        if full_speed:
            return
        delay = size / (rate * 1024 * 1024)
        if stop is not None:
            if stop.wait(delay):
                raise CopyCancelled('Kopiervorgang beendet')
        else:
            time.sleep(delay)

    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_dir() or not target.is_dir():
        raise OSError('Quelle oder Ziel nicht verfügbar')
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Quelle und Ziel überlappen')
    destination = target / source.name
    count, deferred = 0, 0
    candidates, directories = [], []
    if phase:
        phase('Restmenge wird ermittelt …')

    def walk_error(error):
        raise error

    # Snapshot the selected files once. Files arriving later belong to the next
    # run; this makes remaining counts and ETA meaningful during hotfolder use.
    for name in dict.fromkeys(folders):
        if Path(name).name != name or name in {'.', '..'}:
            raise ValueError('Ungültiger Ordner')
        folder = source / name
        if folder.is_symlink() or not folder.is_dir():
            continue
        for root, dirs, files in os.walk(folder, onerror=walk_error):
            check_target()
            root = Path(root)
            dirs[:] = [d for d in dirs if not (root/d).is_symlink() and not (name.lower() == 'prints' and d.lower() == 'thumbs' and not thumbs)]
            out = destination / root.relative_to(source)
            if any(p.is_symlink() for p in [out, *out.parents]):
                raise OSError('Verknüpfung im Zielpfad')
            directories.append(out)
            for name in files:
                check_target()
                src, dst = root/name, out/name
                if src.is_symlink():
                    continue
                if ignore_history and dst.is_symlink():
                    raise VerificationError('Verknüpfung im Ziel: ' + str(dst))
                if not ignore_history and (dst.exists() or dst.is_symlink()):
                    continue
                before = src.stat()
                key = (str(src), before.st_size, before.st_mtime_ns)
                if session_delivered is not None and key in session_delivered:
                    continue
                if journal and not ignore_history and journal.contains(src, before):
                    continue
                if time.time() - before.st_mtime < age:
                    deferred += 1
                    continue
                candidates.append((src, dst, before))
    tracker = TransferProgress({str(src.relative_to(source)): stat.st_size for src, _, stat in candidates},
                               verify, deferred, overall)
    tracker.report(force=True)
    for out in directories:
        check_target()
        if any(p.is_symlink() for p in [out, *out.parents]):
            raise OSError('Verknüpfung im Zielpfad')
        out.mkdir(parents=True, exist_ok=True)

    for src, dst, planned in candidates:
        check_target()
        name = str(src.relative_to(source))
        if not ignore_history and (dst.exists() or dst.is_symlink()):
            tracker.finish(name)
            continue
        before = src.stat()
        if src.is_symlink() or (before.st_size, before.st_mtime_ns) != (planned.st_size, planned.st_mtime_ns):
            tracker.finish(name, deferred=True)
            continue
        if shutil.disk_usage(target).free < before.st_size + 1024 * 1024:
            raise DiskFull('USB-Stick voll. Zweiten Stick auswählen und Fortsetzen drücken.')
        fd, temporary = tempfile.mkstemp(prefix='.hotfolder-', dir=dst.parent)
        os.close(fd)
        try:
            transferred, last_update = 0, 0
            digest = hashlib.sha256() if verify else None
            tracker.start(name, before.st_size)
            if phase:
                phase('Kopieren: ' + name)
            if progress:
                progress(name, 0, before.st_size, count)
            chunk_size = 1024 * 1024 if full_speed else 256 * 1024
            with open(src, 'rb') as incoming, open(temporary, 'wb') as outgoing:
                while True:
                    check_target()
                    chunk = incoming.read(chunk_size)
                    if not chunk:
                        break
                    outgoing.write(chunk)
                    if digest is not None:
                        digest.update(chunk)
                    transferred += len(chunk)
                    throttle(len(chunk))
                    tracker.advance(len(chunk))
                    now = time.monotonic()
                    if progress and now - last_update >= 0.5:
                        progress(name, transferred, before.st_size, count)
                        last_update = now
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if verify:
                tracker.report(force=True)
                if phase:
                    phase('Inhalt prüfen: ' + name)
                actual = hashlib.sha256()
                with open(temporary, 'rb') as copied:
                    while True:
                        check_target()
                        chunk = copied.read(chunk_size)
                        if not chunk:
                            break
                        actual.update(chunk)
                        throttle(len(chunk))
                        tracker.advance(len(chunk), checking=True)
                if actual.digest() != digest.digest():
                    raise VerificationError('Kopierprüfung fehlgeschlagen: ' + name)
            check_target()
            shutil.copystat(src, temporary)
            after = src.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                tracker.finish(name, deferred=True)
                continue
            # Publish without overwriting an existing destination file.
            try:
                if ignore_history:
                    os.replace(temporary, dst)
                elif os.name == 'nt':
                    os.rename(temporary, dst)
                else:
                    os.link(temporary, dst)
            except FileExistsError:
                tracker.finish(name)
                continue
            if journal:
                journal.record(src, before, volume, verified=verify)
            if session_delivered is not None:
                session_delivered.add((str(src), before.st_size, before.st_mtime_ns))
            count += 1
            tracker.finish(name, delivered=True)
            if progress:
                progress(name, before.st_size, before.st_size, count)
        except OSError as error:
            if error.errno == errno.ENOSPC or getattr(error, 'winerror', None) in {39, 112}:
                raise DiskFull('USB-Stick voll. Zweiten Stick auswählen und Fortsetzen drücken.') from error
            raise
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
    return count
