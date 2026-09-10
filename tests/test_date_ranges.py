import unittest

from src.tools.date_ranges import exclusive_end_date


class TestDateRanges(unittest.TestCase):
    def test_inclusive_end_date_becomes_next_midnight(self):
        self.assertEqual(exclusive_end_date("2026-09-09"), "2026-09-10")


if __name__ == "__main__":
    unittest.main()
