"""Dev server: the real backend router under /api/plugins/roomsmith plus the
harness page. Data goes to a scratch folder (ROOMSMITH_DATA_DIR) so nothing
touches a Hermes home.

    .venv/bin/python web/dev/server.py [--port 8765] [--data /tmp/rs-dev]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default=str(ROOT / ".scratch" / "dev-data"))
    args = ap.parse_args()
    os.environ["ROOMSMITH_DATA_DIR"] = args.data
    Path(args.data).mkdir(parents=True, exist_ok=True)

    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_roomsmith", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    app = FastAPI(title="Roomsmith dev")
    app.include_router(mod.router, prefix="/api/plugins/roomsmith")
    dev = ROOT / "web" / "dev"

    @app.post("/dev/agent/{project_id}")
    async def agent_command(project_id: str, body: dict):
        """Harness only: an edit made the way the agent's tools make it (actor "agent"), from another caller
        than the editor. The plugin's own API always records its caller as the user."""
        return mod._svc().apply({"project_id": project_id, "actor": "agent", "operations": body.get("operations")})

    @app.get("/")
    async def index():
        return FileResponse(dev / "index.html")

    app.mount("/", StaticFiles(directory=str(dev)), name="dev")
    print(f"Roomsmith dev harness: http://127.0.0.1:{args.port}/  (data in {args.data})")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
