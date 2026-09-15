from types import SimpleNamespace

from scripts.run_conflict_e2e import evaluate_result


def _expectations() -> dict:
    return {
        "sample": "conflict",
        "conflict": {
            "metric_key": "revenue",
            "period_year": 2020,
            "expected_loser_value": 10.0,
            "expected_winner_value": 20.0,
            "absolute_tolerance": 0.01,
        },
    }


def _observation(value: float, doc_id: str, *, grounded: bool = True):
    return SimpleNamespace(
        value=value,
        document_id=doc_id,
        provenance={"source_grounded": grounded},
    )


def test_conflict_e2e_requires_real_loser_warning_and_grounded_winner() -> None:
    report = evaluate_result(
        expectations=_expectations(),
        ingest_results=[
            {"status": "completed", "doc_id": "old"},
            {"status": "completed", "doc_id": "new"},
        ],
        first_observations=[_observation(10.0, "old")],
        final_observations=[_observation(20.0, "new")],
        winner_warnings=["conflicting revenue values for 2020; kept document new"],
    )

    assert report["passed"] is True
    assert all(report["checks"].values())


def test_conflict_e2e_rejects_silent_or_ungrounded_resolution() -> None:
    report = evaluate_result(
        expectations=_expectations(),
        ingest_results=[
            {"status": "completed", "doc_id": "old"},
            {"status": "completed", "doc_id": "new"},
        ],
        first_observations=[_observation(10.0, "old")],
        final_observations=[_observation(20.0, "new", grounded=False)],
        winner_warnings=[],
    )

    assert report["passed"] is False
    assert report["checks"]["conflict_warning_persisted"] is False
    assert report["checks"]["winner_grounded"] is False
