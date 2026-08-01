"""Unit tests for L4 multi-sample profile helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.run_l4_research_eval import (
    DEFAULT_GOLDEN,
    L4_THRESHOLDS,
    _gate_status,
    resolve_l4_samples,
)


def test_resolve_l4_samples_profiles() -> None:
    smoke = resolve_l4_samples(profile="smoke", expectations=None)
    assert [item["name"] for item in smoke] == ["znz_2021"]

    regression = resolve_l4_samples(profile="regression", expectations=None)
    assert [item["name"] for item in regression] == ["jucan_2021", "tianhua_2021"]

    all_samples = resolve_l4_samples(profile="all", expectations=None)
    assert [item["name"] for item in all_samples] == [
        "znz_2021",
        "jucan_2021",
        "tianhua_2021",
    ]


def test_resolve_l4_samples_defaults_to_znz() -> None:
    samples = resolve_l4_samples(profile=None, expectations=None)
    assert len(samples) == 1
    assert samples[0]["golden"] == DEFAULT_GOLDEN


def test_resolve_l4_samples_custom_expectations() -> None:
    path = Path("data/golden/jucan_2021_stage_expectations.json")
    samples = resolve_l4_samples(profile=None, expectations=path)
    assert samples[0]["name"] == "jucan_2021"
    assert samples[0]["golden"] == path


def test_gate_status_thresholds() -> None:
    assert L4_THRESHOLDS["smoke_full_pass_rate"] == 1.0
    assert L4_THRESHOLDS["retrieval_only_pass_rate"] == 1.0
    assert L4_THRESHOLDS["regression_full_min_pass_rate"] == 0.8

    smoke = {"role": "smoke"}
    assert _gate_status(smoke, 1.0, retrieval_only=False)["met"] is True
    assert _gate_status(smoke, 0.875, retrieval_only=False)["met"] is False

    regression = {"role": "regression"}
    soft = _gate_status(regression, 0.8, retrieval_only=False)
    assert soft["kind"] == "regression_full_soft"
    assert soft["met"] is True
    assert _gate_status(regression, 0.79, retrieval_only=False)["met"] is False
