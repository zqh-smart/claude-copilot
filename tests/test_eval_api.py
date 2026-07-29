from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_eval_serving_list_and_detail(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    serving = reports / "serving_eval"
    serving.mkdir(parents=True)
    payload = {
        "doc_id": "doc-abc",
        "ingest_seconds": 1.2,
        "segment_count": 10,
        "company_id": "company-x",
        "backends": {"embedding": "silicon"},
        "l3": {
            "total": 2,
            "passed": 2,
            "pass_rate": 1.0,
            "cases": [
                {"id": "q1", "passed": True, "route_ok": True},
                {"id": "q2", "passed": True, "route_ok": True},
            ],
        },
    }
    (serving / "doc-abc_serving_eval.json").write_text(
        __import__("json").dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPORT_DATA_PATH", str(reports))
    from app.core.config import get_settings

    get_settings.cache_clear()

    client = TestClient(app)
    listed = client.get("/api/v1/eval/serving")
    assert listed.status_code == 200
    assert listed.json()[0]["doc_id"] == "doc-abc"
    assert listed.json()[0]["l3"]["pass_rate"] == 1.0

    detail = client.get("/api/v1/eval/serving/doc-abc")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 2

    get_settings.cache_clear()


def test_eval_scorecards_list(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    eval_dir = reports / "eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "latest_scorecard.json").write_text(
        __import__("json").dumps(
            {
                "summary_scores": {"core_metric_exact_match": 1.0},
                "serving_gate": {"allow_metric_serving": True},
                "retrieval_cases": [{"id": "q1"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPORT_DATA_PATH", str(reports))
    from app.core.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    response = client.get("/api/v1/eval/scorecards")
    assert response.status_code == 200
    assert response.json()[0]["summary_scores"]["core_metric_exact_match"] == 1.0
    get_settings.cache_clear()
