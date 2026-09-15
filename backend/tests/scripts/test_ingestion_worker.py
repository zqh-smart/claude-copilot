from unittest.mock import MagicMock, patch

from scripts.run_ingestion_worker import run_worker_iteration


def test_worker_iteration_dispatches_persisted_jobs() -> None:
    service = MagicMock()
    service.recover_incomplete.return_value = 3
    with patch(
        "scripts.run_ingestion_worker.get_ingestion_job_service",
        return_value=service,
    ):
        assert run_worker_iteration() == 3
    service.recover_incomplete.assert_called_once_with()
