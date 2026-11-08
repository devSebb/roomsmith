"""Roomsmith engine.

Standard library only. Never imports Hermes. Every public function takes plain
dicts (the scene JSON) or a database path, so the same code runs unchanged inside
the agent process, inside the dashboard backend process, and under pytest.

Conventions (see docs/ROOMSMITH_PLAN.md section 6):
- units: metres and radians
- right-handed, +Y up, floor at Y = 0
- an object's front faces -Z at yaw 0; yaw rotates about +Y
- the room outline is a simple polygon in the X-Z plane, stored so that the
  shoelace sum over (x, z) is positive; wall i joins vertex i to vertex i + 1
"""

from rs_core.model import SCHEMA_VERSION  # noqa: F401

__version__ = "0.1.0"
