from scripts import run_acceptance_suite
from scripts.run_acceptance_suite import build_parser


def test_acceptance_defaults_to_api_and_invariant_checks() -> None:
    args = build_parser().parse_args([])
    assert args.with_api is True
    assert args.skip_invariants is False


def test_acceptance_allows_explicitly_skipping_external_api_check() -> None:
    args = build_parser().parse_args(["--skip-api", "--skip-invariants"])
    assert args.with_api is False
    assert args.skip_invariants is True


def test_acceptance_exposes_scanned_pdf_stress_profile() -> None:
    args = build_parser().parse_args(["--profile", "stress"])
    assert args.profile == "stress"


def test_acceptance_exposes_scanned_table_stress_profile() -> None:
    args = build_parser().parse_args(["--profile", "table-stress"])
    assert args.profile == "table-stress"


def test_acceptance_exposes_real_pdf_conflict_profile() -> None:
    args = build_parser().parse_args(["--profile", "conflict"])
    assert args.profile == "conflict"


def test_acceptance_exposes_postgres_worker_soak_profile() -> None:
    args = build_parser().parse_args(["--profile", "soak"])
    assert args.profile == "soak"


def test_worker_profile_runs_event_wakeup_before_concurrency_soak(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        run_acceptance_suite,
        "_run",
        lambda command: commands.append(command) or 0,
    )

    assert run_acceptance_suite._run_worker_soak() == 0
    assert commands[0][-1].endswith("run_ingestion_worker_wakeup_smoke.py")
    assert commands[1][-1].endswith("run_ingestion_worker_soak.py")


def test_acceptance_exposes_l4_hard_gate_profile() -> None:
    args = build_parser().parse_args(["--profile", "l4"])
    assert args.profile == "l4"


def test_l4_profile_runs_full_all_sample_gate(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        run_acceptance_suite,
        "_run",
        lambda command: commands.append(command) or 0,
    )

    assert run_acceptance_suite._run_l4() == 0
    assert commands[0][-2:] == ["--profile", "all"]
