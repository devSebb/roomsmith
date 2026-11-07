import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rs_core.service import RoomService  # noqa: E402


@pytest.fixture
def svc(tmp_path):
    s = RoomService(tmp_path / "data.db", tmp_path)
    yield s
    s.close()


@pytest.fixture
def room(svc):
    """A 4 x 5 x 2.5 m room with a door on the left wall and a window on the back wall."""
    r = svc.create_project("Test room", 4.0, 5.0, 2.5)
    pid = r["project_id"]
    res = svc.apply(
        {
            "project_id": pid,
            "operations": [
                {"op": "add_opening", "wall_id": "w4", "kind": "door", "offset_m": 0.5, "width_m": 0.9},
                {"op": "add_opening", "wall_id": "w1", "kind": "window", "offset_m": 1.5, "width_m": 1.2, "sill_m": 0.9, "height_m": 1.2},
            ],
        }
    )
    assert res["ok"], res
    return pid
