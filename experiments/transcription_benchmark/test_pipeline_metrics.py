from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from pipeline_metrics import calculate, elapsed_between, hypothesis, require_isolated


class PipelineMetricsTests(unittest.TestCase):
    def settings(self, **changes):
        values = dict(APP_ENV="test", DATABASE_URL="postgresql+psycopg://synthetic@postgres/usagi_whisper_benchmark",
                      REDIS_URL="redis://redis:6379/0")
        values.update(changes)
        return SimpleNamespace(**values)

    def test_refuses_product_database(self):
        with self.assertRaises(RuntimeError):
            require_isolated(self.settings(DATABASE_URL="postgresql+psycopg://synthetic@postgres/transcription_db"))

    def test_refuses_paid_credentials(self):
        for name in ("AAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "PROVIDER_CREDENTIAL_ENCRYPTION_KEY"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                require_isolated(self.settings(**{name: "synthetic-not-a-real-key"}))

    def test_accepts_only_disposable_context(self):
        require_isolated(self.settings())

    def test_missing_stage_is_unknown_not_zero(self):
        row = calculate({}, upload_seconds=1, end_to_end_seconds=5, queue_seconds=None)
        self.assertIsNone(row["asr_seconds"])
        self.assertIsNone(row["processing_rtf"])
        self.assertIsNone(row["queue_seconds"])

    def test_rtf_is_worker_elapsed_not_only_asr(self):
        row = calculate(dict(audio_seconds=60, worker_seconds=120, asr_seconds=30),
                        upload_seconds=1, end_to_end_seconds=180, queue_seconds=59)
        self.assertEqual(row["processing_rtf"], 2)
        self.assertEqual(row["end_to_end_rtf"], 3)

    def test_metadata_cannot_publish_transcript_or_secret(self):
        row = calculate(dict(transcript="private", api_key="synthetic", filename="private",
                             cpu_seconds=2), upload_seconds=1, end_to_end_seconds=2, queue_seconds=0)
        self.assertNotIn("transcript", row)
        self.assertNotIn("api_key", row)
        self.assertNotIn("filename", row)

    def test_invalid_number_is_not_evidence(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(dict(worker_seconds=value), upload_seconds=1, end_to_end_seconds=2, queue_seconds=0)

    def test_queue_uses_server_timestamps_and_detects_clock_reversal(self):
        start = datetime(2026, 10, 14, tzinfo=timezone.utc)
        self.assertEqual(elapsed_between(start, start + timedelta(seconds=3)), 3)
        self.assertIsNone(elapsed_between(start, start - timedelta(seconds=1)))

    def test_preserves_persisted_segment_order_for_scoring(self):
        self.assertEqual(hypothesis([{"text": "uma"}, {"text": "reunião"}]), "uma reunião")


if __name__ == "__main__":
    unittest.main()
