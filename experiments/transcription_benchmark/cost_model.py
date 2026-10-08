"""Scenario cost and queue estimates for measured transcription benchmarks.

This is a planning simulator, not a production cost ledger or a commercial plan.
Capacity is unknown until a concurrency-specific measured RTF profile is supplied.
"""

from __future__ import annotations

import argparse
import heapq
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ZERO = Decimal("0")
ONE = Decimal("1")
SECONDS_PER_HOUR = Decimal("3600")


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal number")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal number")
    return result


def _nonnegative(value: Any, field: str) -> Decimal:
    result = _decimal(value, field)
    if result < ZERO:
        raise ValueError(f"{field} cannot be negative")
    return result


def _money_inputs(config: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    currency = config.get("currency")
    if not isinstance(currency, str) or not currency:
        raise ValueError("currency is required")
    options = config.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a non-empty list")
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("each option must be an object")
        price = option.get("price", {})
        if price.get("currency", currency) != currency:
            raise ValueError(
                f"currency mismatch for {option.get('name', 'unnamed option')}: "
                f"{price.get('currency')} != {currency}"
            )
    return currency, options


def _price(option: dict[str, Any], audio_hours: Decimal, jobs: Decimal,
           base_rtf: Decimal | None, startup_seconds: Decimal = ZERO) -> dict[str, Any]:
    price = option.get("price", {})
    fixed = _nonnegative(price.get("fixed_monthly", 0), "fixed_monthly")
    setup = _nonnegative(price.get("setup_fee", 0), "setup_fee")
    amortization_months = _nonnegative(
        price.get("setup_amortization_months", 0), "setup_amortization_months"
    )
    if setup > ZERO and amortization_months == ZERO:
        raise ValueError("setup_amortization_months must be positive when setup_fee is positive")
    setup_monthly = setup / amortization_months if amortization_months else ZERO
    other = _nonnegative(price.get("other_monthly", 0), "other_monthly")
    variable = _nonnegative(
        price.get("variable_per_audio_hour", 0), "variable_per_audio_hour"
    ) * audio_hours
    compute_rate = _nonnegative(
        price.get("hourly_compute_rate", 0), "hourly_compute_rate"
    )
    compute = None
    if compute_rate == ZERO:
        compute = ZERO
    elif base_rtf is not None:
        compute = compute_rate * (
            audio_hours * base_rtf + jobs * startup_seconds / SECONDS_PER_HOUR
        )
    base = fixed + setup_monthly + other
    partial_total = base + variable + (compute if compute is not None else ZERO)
    return {
        "fixed_monthly": fixed,
        "setup_amortized_monthly": setup_monthly,
        "other_monthly": other,
        "variable_usage": variable,
        "compute_usage": compute,
        "partial_total": partial_total,
        "total": partial_total if compute is not None else None,
        "total_status": "complete" if compute is not None else "unknown_hourly_compute_cost_without_measured_rtf",
    }


def _profile(option: dict[str, Any], concurrency: int,
             average_job_audio_hours: Decimal) -> dict[str, Decimal] | None:
    measurements = option.get("measurements", {})
    profiles = measurements.get("by_concurrency", {})
    profile = profiles.get(str(concurrency))
    if profile is None:
        return None
    transcribe = _nonnegative(profile.get("transcription_rtf"), "transcription_rtf")
    diarize = _nonnegative(profile.get("diarization_rtf", 0), "diarization_rtf")
    startup = _nonnegative(
        profile.get("startup_seconds_per_job", measurements.get("startup_seconds_per_job", 0)),
        "startup_seconds_per_job",
    )
    if average_job_audio_hours <= ZERO:
        raise ValueError("average_job_audio_hours must be positive for measured capacity")
    effective = transcribe + diarize + startup / SECONDS_PER_HOUR / average_job_audio_hours
    return {
        "transcription_rtf": transcribe,
        "diarization_rtf": diarize,
        "startup_seconds_per_job": startup,
        "base_rtf": transcribe + diarize,
        "effective_rtf": effective,
    }


def _queue(arrivals: list[dict[str, Any]], concurrency: int,
           base_rtf: Decimal, startup_seconds: Decimal,
           max_queue_hours: Decimal) -> dict[str, Any]:
    """FIFO deterministic lane simulation; every job uses measured profile at N."""
    lanes = [ZERO] * concurrency
    heapq.heapify(lanes)
    rows = []
    max_wait = ZERO
    late = 0
    previous_arrival = ZERO
    for index, job in enumerate(arrivals):
        arrival = _nonnegative(job.get("arrival_hour"), "arrival_hour")
        if index and arrival < previous_arrival:
            raise ValueError("arrivals must be ordered by arrival_hour")
        previous_arrival = arrival
        audio = _nonnegative(job.get("audio_hours"), "audio_hours")
        if audio <= ZERO:
            raise ValueError("arrival audio_hours must be positive")
        available = heapq.heappop(lanes)
        start = max(arrival, available)
        wait = start - arrival
        finish = start + audio * base_rtf + startup_seconds / SECONDS_PER_HOUR
        heapq.heappush(lanes, finish)
        max_wait = max(max_wait, wait)
        late += int(wait > max_queue_hours)
        rows.append({
            "job": index,
            "arrival_hour": arrival,
            "start_hour": start,
            "finish_hour": finish,
            "queue_wait_hours": wait,
        })
    return {
        "method": "deterministic_arrival_schedule_fixed_measured_concurrency_profile",
        "maximum_queue_wait_hours": max_wait,
        "jobs_over_max_queue_hours": late,
        "max_queue_hours": max_queue_hours,
        "jobs": rows,
    }


def simulate(config: dict[str, Any]) -> dict[str, Any]:
    currency, options = _money_inputs(config)
    audio_hours = _nonnegative(config.get("audio_hours_sent", 0), "audio_hours_sent")
    jobs = _nonnegative(config.get("jobs", 0), "jobs")
    average_job = _nonnegative(config.get("average_job_audio_hours", 0), "average_job_audio_hours")
    concurrency_raw = config.get("concurrency", 1)
    if isinstance(concurrency_raw, bool) or int(concurrency_raw) != concurrency_raw:
        raise ValueError("concurrency must be a positive integer")
    concurrency = int(concurrency_raw)
    if concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    monthly_hours = _nonnegative(config.get("monthly_hours_available", 720), "monthly_hours_available")
    target = _decimal(config.get("target_utilization", "0.75"), "target_utilization")
    if not ZERO < target <= ONE:
        raise ValueError("target_utilization must be in (0, 1]")
    max_queue = _nonnegative(config.get("max_queue_hours", 24), "max_queue_hours")
    arrivals = config.get("arrivals")
    if arrivals is not None and not isinstance(arrivals, list):
        raise ValueError("arrivals must be a list of deterministic arrival jobs")

    results = []
    for option in options:
        profile = _profile(option, concurrency, average_job) if option.get("measurements", {}).get("by_concurrency") else None
        rtf = profile["effective_rtf"] if profile else None
        if profile:
            processable = monthly_hours * concurrency * target / rtf if rtf > ZERO else None
            sent_wall = (
                audio_hours * profile["base_rtf"]
                + jobs * profile["startup_seconds_per_job"] / SECONDS_PER_HOUR
            )
            capacity = {
                "status": "measured_profile",
                "concurrency": concurrency,
                "target_utilization": target,
                "effective_rtf": rtf,
                "audio_hours_processable_monthly": processable,
                "wall_hours_for_sent_work": sent_wall,
                "fits_monthly_target_capacity": audio_hours <= processable if processable is not None else None,
            }
            queue = (
                _queue(
                    arrivals,
                    concurrency,
                    profile["base_rtf"],
                    profile["startup_seconds_per_job"],
                    max_queue,
                )
                if arrivals is not None else None
            )
        else:
            processable = None
            capacity = {
                "status": "unknown_until_measured_rtf",
                "concurrency": concurrency,
                "target_utilization": target,
                "audio_hours_processable_monthly": None,
                "wall_hours_for_sent_work": None,
                "fits_monthly_target_capacity": None,
            }
            queue = None
        results.append({
            "name": option.get("name", "unnamed"),
            "kind": option.get("kind", "unspecified"),
            "capacity": capacity,
            "queue": queue,
            "cost": _price(
                option,
                audio_hours,
                jobs,
                profile["base_rtf"] if profile else None,
                profile["startup_seconds_per_job"] if profile else ZERO,
            ),
        })

    break_even = []
    for local in results:
        if local["kind"] != "self_hosted":
            continue
        local_option = next(item for item in options if item.get("name", "unnamed") == local["name"])
        for provider in results:
            if provider["kind"] != "provider":
                continue
            provider_option = next(item for item in options if item.get("name", "unnamed") == provider["name"])
            local_variable = _nonnegative(local_option.get("price", {}).get("variable_per_audio_hour", 0), "variable_per_audio_hour")
            provider_variable = _nonnegative(provider_option.get("price", {}).get("variable_per_audio_hour", 0), "variable_per_audio_hour")
            local_compute = _nonnegative(local_option.get("price", {}).get("hourly_compute_rate", 0), "hourly_compute_rate")
            local_profile = _profile(local_option, concurrency, average_job) if local_option.get("measurements", {}).get("by_concurrency") else None
            if local_profile is None:
                threshold = None
                status = "unknown_until_measured_rtf"
            else:
                effective_rtf = local_profile["effective_rtf"]
                per_audio = local_variable + local_compute * effective_rtf
                provider_base = provider["cost"]["fixed_monthly"] + provider["cost"]["setup_amortized_monthly"] + provider["cost"]["other_monthly"]
                local_base = local["cost"]["fixed_monthly"] + local["cost"]["setup_amortized_monthly"] + local["cost"]["other_monthly"]
                difference = provider_variable - per_audio
                threshold = (local_base - provider_base) / difference if difference > ZERO else None
                status = "estimated" if threshold is not None and threshold >= ZERO else "no_positive_break_even"
            break_even.append({
                "self_hosted": local["name"],
                "provider": provider["name"],
                "status": status,
                "audio_hours_per_month": threshold,
            })

    return {
        "estimate_only": True,
        "not_a_cost_ledger_or_commercial_plan": True,
        "currency": currency,
        "audio_hours_sent": audio_hours,
        "jobs": jobs,
        "concurrency": concurrency,
        "monthly_hours_available": monthly_hours,
        "target_utilization": target,
        "capacity_note": "Single-worker RTF is never multiplied by concurrency; the exact concurrency profile must be measured.",
        "queue_note": "Queue delay is reported only for supplied deterministic arrivals; monthly averages do not establish real queue latency.",
        "options": results,
        "break_even": break_even,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Cannot encode {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="JSON scenario input")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"), parse_float=Decimal)
    result = simulate(config)
    rendered = json.dumps(result, indent=2, default=_json_default) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
