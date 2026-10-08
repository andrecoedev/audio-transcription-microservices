import unittest

from summarize import summarize


class SummaryTests(unittest.TestCase):
    def test_never_calls_cpu_a_gpu(self):
        with self.assertRaises(ValueError):
            summarize([{"status": "completed", "actual_device": "cpu", "requested_device": "cuda"}])

    def test_failures_are_not_successful_samples(self):
        self.assertEqual(summarize([{"status": "failed"}]), [])

    def test_requires_three_distinct_sessions(self):
        row = {"status": "completed", "actual_device": "cpu", "fixture_id": "public",
               "engine": "faster-whisper", "model": "tiny", "phase": "warm", "session": 1,
               "inference_seconds": 2}
        summary = summarize([row, row, row])[0]
        self.assertFalse(summary["repeated_enough"])


if __name__ == "__main__":
    unittest.main()
