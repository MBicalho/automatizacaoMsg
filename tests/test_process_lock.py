import tempfile
from pathlib import Path
import unittest

from scheduler import AlreadyRunningError, ProcessLock


class ProcessLockTests(unittest.TestCase):
    def test_single_lock_acquires_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "test.lock"
            with ProcessLock(lock_path) as lock:
                self.assertTrue(lock_path.exists())
            self.assertFalse(lock_path.exists())

    def test_concurrent_lock_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "test.lock"
            with ProcessLock(lock_path):
                # Segunda tentativa deve falhar
                lock2 = ProcessLock(lock_path)
                with self.assertRaises(AlreadyRunningError):
                    lock2.acquire()


if __name__ == "__main__":
    unittest.main()
