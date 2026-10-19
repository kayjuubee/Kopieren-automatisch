import unittest
from startup import BoothSession


class SessionTests(unittest.TestCase):
    def test_only_launch_on_booth_start_and_keep_manual_exit(self):
        session = BoothSession()
        self.assertFalse(session.should_launch({'explorer.exe'}, False))
        self.assertTrue(session.should_launch({'dslrBooth.exe'}, False))
        self.assertFalse(session.should_launch({'dslrBooth.exe'}, False))
        self.assertFalse(session.should_launch(set(), False))
        self.assertTrue(session.should_launch({'lumaBooth.exe'}, False))

    def test_already_running_and_overlapping_booth_sessions(self):
        session = BoothSession()
        self.assertFalse(session.should_launch({'dslrBooth.exe'}, True))
        self.assertFalse(session.should_launch({'lumaBooth.exe', 'dslrBooth.exe'}, False))
