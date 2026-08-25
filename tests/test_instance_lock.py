"""
Unit tests for SingleInstanceLock.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from utils.instance_lock import SingleInstanceLock


class TestSingleInstanceLock(unittest.TestCase):
    def test_acquire_and_release(self):
        lock1 = SingleInstanceLock("test_instance_lock_1")
        self.assertTrue(lock1.acquire())

        # Second lock with same name should fail to acquire
        lock2 = SingleInstanceLock("test_instance_lock_1")
        self.assertFalse(lock2.acquire())

        # Release first lock
        lock1.release()

        # Now lock2 or lock3 can acquire
        lock3 = SingleInstanceLock("test_instance_lock_1")
        self.assertTrue(lock3.acquire())
        lock3.release()


if __name__ == "__main__":
    unittest.main()
