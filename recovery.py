"""Bounded retries for recurring copy errors; never display a dialog."""
from collections import Counter

from copier import CopyCancelled


class RepeatedCopyError(Exception):
    def __init__(self, error):
        self.original = error
        super().__init__(f'Derselbe Kopierfehler ist 5-mal aufgetreten: {error}')


def error_key(error):
    code = getattr(error, 'winerror', None) or error.errno
    return type(error).__name__, code if code is not None else str(error)


def retry_copy(operation, stop, notify=None, delay=3):
    failures = Counter()
    while True:
        if stop.is_set():
            raise CopyCancelled('Kopiervorgang beendet')
        try:
            return operation()
        except OSError as error:
            key = error_key(error)
            failures[key] += 1
            count = failures[key]
            if count >= 5:
                raise RepeatedCopyError(error) from error
            if notify:
                notify(error, count)
            if stop.wait(delay):
                raise CopyCancelled('Kopiervorgang beendet')
