from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
START_SCRIPT = PROJECT_ROOT / "start.sh"


def test_start_script_exposes_project_root_to_seed_script() -> None:
    """The production seed command must be able to import the ``app`` package."""
    content = START_SCRIPT.read_text()

    assert 'export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"' in content
    assert content.index("export PYTHONPATH") < content.index("alembic upgrade head")
    assert content.index("export PYTHONPATH") < content.index("python scripts/seed_demo_data.py")
