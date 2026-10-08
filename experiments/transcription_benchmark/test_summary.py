import unittest

from summarize import exportable_rows, summarize


class SummaryTests(unittest.TestCase):
    def test_export_cannot_include_debug_transcripts_or_credentials(self):
        rows = [{"fixture_id": "fleurs-quality", "rtf": 0.1,
                 "transcript": "private content", "api_key": "not-a-real-secret", "file_path": "private"}]
        self.assertEqual(exportable_rows(rows), [{"fixture_id": "fleurs-quality", "rtf": 0.1}])

    def test_public_export_excludes_private_audio_fingerprint(self):
        self.assertEqual(exportable_rows([{"fixture_id": "local-video-001", "audio_sha256": "private-fingerprint"}], True), [])

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
