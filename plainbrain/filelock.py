"""One writer at a time, through an operating-system lock on a lock file.

The lock belongs to an open file handle, so the operating system releases it when the holder exits or crashes.
There is no stale lock to clear, and no waiter can delete the lock another writer holds. The lock file stays in
place between writes; `*.lock` is ignored by git.
"""
import os
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt

    def _try_lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def hold(path: Path, wait_seconds: float, busy: Exception):
    """Hold the lock on `path` for the block, or raise `busy` after `wait_seconds`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                _try_lock(handle)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise busy
                time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()
