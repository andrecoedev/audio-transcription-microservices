import unittest
from decimal import Decimal

from cost_model import simulate


def option(name, kind, price, profiles=None):
    return {
        "name": name,
        "kind": kind,
        "price": {"currency": "USD", **price},
        "measurements": {"by_concurrency": profiles or {}},
    }


class CostModelTests(unittest.TestCase):
    def config(self, options, **overrides):
        config = {
            "currency": "USD",
            "audio_hours_sent": 10,
            "jobs": 20,
            "average_job_audio_hours": 0.5,
            "concurrency": 1,
            "monthly_hours_available": 720,
            "target_utilization": "0.75",
            "options": options,
        }
        config.update(overrides)
        return config

    def test_capacity_is_unknown_without_measured_rtf(self):
        result = simulate(self.config([option("cpu", "self_hosted", {"fixed_monthly": 5})]))
        capacity = result["options"][0]["capacity"]
        self.assertEqual(capacity["status"], "unknown_until_measured_rtf")
        self.assertIsNone(capacity["audio_hours_processable_monthly"])

    def test_capacity_uses_measured_transcription_diarization_and_startup(self):
        measured = option("cpu", "self_hosted", {"fixed_monthly": 5}, {
            "1": {
                "transcription_rtf": "2",
                "diarization_rtf": "0.5",
                "startup_seconds_per_job": 180,
            }
        })
        result = simulate(self.config([measured]))["options"][0]["capacity"]
        self.assertEqual(result["effective_rtf"], Decimal("2.6"))
        self.assertEqual(result["audio_hours_processable_monthly"], Decimal("207.6923076923076923076923077"))
        self.assertEqual(result["wall_hours_for_sent_work"], Decimal("26"))

    def test_never_scales_single_worker_profile_to_higher_concurrency(self):
        measured = option("cpu", "self_hosted", {"fixed_monthly": 5}, {
            "1": {"transcription_rtf": 2},
        })
        result = simulate(self.config([measured], concurrency=4))["options"][0]
        self.assertEqual(result["capacity"]["status"], "unknown_until_measured_rtf")

    def test_setup_amortization_and_variable_usage_use_decimal(self):
        measured = option("gpu", "self_hosted", {
            "fixed_monthly": "100", "setup_fee": "120", "setup_amortization_months": 12,
            "other_monthly": "5", "hourly_compute_rate": "0.25",
        }, {"1": {
            "transcription_rtf": "2",
            "startup_seconds_per_job": 180,
        }})
        result = simulate(self.config([measured]))["options"][0]
        self.assertEqual(result["cost"]["setup_amortized_monthly"], Decimal("10"))
        self.assertEqual(result["cost"]["compute_usage"], Decimal("5.25"))
        self.assertEqual(result["cost"]["total"], Decimal("120.25"))

    def test_hourly_compute_cost_is_unknown_until_rtf_is_measured(self):
        measured_cost = option("cpu", "self_hosted", {
            "fixed_monthly": "10", "hourly_compute_rate": "0.5",
        })
        cost = simulate(self.config([measured_cost]))["options"][0]["cost"]
        self.assertIsNone(cost["compute_usage"])
        self.assertIsNone(cost["total"])
        self.assertEqual(cost["partial_total"], Decimal("10"))
        self.assertEqual(cost["total_status"], "unknown_hourly_compute_cost_without_measured_rtf")

    def test_setup_fee_requires_amortization_period(self):
        option_with_setup = option("gpu", "self_hosted", {
            "fixed_monthly": "100", "setup_fee": "120",
        })
        with self.assertRaisesRegex(ValueError, "setup_amortization_months must be positive"):
            simulate(self.config([option_with_setup]))

    def test_mixed_currencies_rejected(self):
        bad = option("eur", "provider", {"fixed_monthly": 5})
        bad["price"]["currency"] = "EUR"
        with self.assertRaisesRegex(ValueError, "currency mismatch"):
            simulate(self.config([bad]))

    def test_queue_requires_arrivals_and_uses_deterministic_waits(self):
        measured = option("cpu", "self_hosted", {"fixed_monthly": 5}, {
            "1": {"transcription_rtf": 2},
        })
        result = simulate(self.config([measured], arrivals=[
            {"arrival_hour": 0, "audio_hours": 1},
            {"arrival_hour": 0, "audio_hours": 1},
        ], max_queue_hours=1))["options"][0]["queue"]
        self.assertEqual(result["maximum_queue_wait_hours"], Decimal("2"))
        self.assertEqual(result["jobs_over_max_queue_hours"], 1)

    def test_queue_uses_each_jobs_audio_length_and_fixed_startup(self):
        measured = option("cpu", "self_hosted", {"fixed_monthly": 5}, {
            "1": {
                "transcription_rtf": 2,
                "startup_seconds_per_job": 180,
            },
        })
        queue = simulate(self.config([measured], arrivals=[
            {"arrival_hour": 0, "audio_hours": "0.25"},
            {"arrival_hour": 0, "audio_hours": "1.25"},
        ]))["options"][0]["queue"]
        self.assertEqual(queue["maximum_queue_wait_hours"], Decimal("0.55"))
        self.assertEqual(queue["jobs"][0]["finish_hour"], Decimal("0.55"))

    def test_break_even_waits_for_measured_local_rtf(self):
        local = option("local", "self_hosted", {"fixed_monthly": 20})
        provider = option("api", "provider", {"variable_per_audio_hour": "0.2"})
        result = simulate(self.config([local, provider]))
        self.assertEqual(result["break_even"][0]["status"], "unknown_until_measured_rtf")
        self.assertIsNone(result["break_even"][0]["audio_hours_per_month"])


if __name__ == "__main__":
    unittest.main()
