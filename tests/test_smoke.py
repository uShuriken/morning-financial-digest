from pathlib import Path


def test_digest_script_exists() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assert (project_root / "digest.py").exists()
