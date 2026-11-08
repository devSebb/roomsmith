"""Backend routes through FastAPI's test client, loaded the way Hermes loads
them: standalone module, no package, plugin root on sys.path."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_roomsmith", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod._service = None
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/roomsmith")
    with TestClient(app) as c:
        yield c
    if mod._service:
        mod._service.close()


def test_health_and_crud(client):
    h = client.get("/api/plugins/roomsmith/health").json()
    assert h["ok"] and h["schema_version"] == 1
    r = client.post("/api/plugins/roomsmith/projects", json={"name": "Office", "width_m": 3.6, "depth_m": 4.2, "height_m": 2.5})
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    assert client.get(f"/api/plugins/roomsmith/projects/{pid}/head").json()["revision"] == 1
    r = client.post(
        f"/api/plugins/roomsmith/projects/{pid}/commands",
        json={"expected_revision": 1, "operations": [{"op": "add_object", "name": "Desk", "category": "desk", "place": {"against_wall": "w1"}}]},
    )
    assert r.status_code == 200 and r.json()["revision"] == 2
    conflict = client.post(f"/api/plugins/roomsmith/projects/{pid}/commands", json={"expected_revision": 1, "operations": [{"op": "set_room_height", "height_m": 2.7}]})
    assert conflict.status_code == 409
    bad = client.post(f"/api/plugins/roomsmith/projects/{pid}/commands", json={"operations": [{"op": "move_object", "id": "zz", "by": [1, 0]}]})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "unknown_id"
    s = client.get(f"/api/plugins/roomsmith/projects/{pid}/scene").json()
    assert s["ok"] and len(s["scene"]["objects"]) == 1 and s["can_undo"] is True
    assert client.post(f"/api/plugins/roomsmith/projects/{pid}/undo", json={}).json()["revision"] == 3
    assert client.post(f"/api/plugins/roomsmith/projects/{pid}/redo", json={}).json()["revision"] == 4
    hist = client.get(f"/api/plugins/roomsmith/projects/{pid}/history").json()
    assert hist["revisions"][0]["actor"] == "user"
    chk = client.post(f"/api/plugins/roomsmith/projects/{pid}/check", json={"question": "where_fits", "dimensions_m": [0.8, 2, 0.3]}).json()
    assert chk["ok"]
    prod = client.post(f"/api/plugins/roomsmith/projects/{pid}/products", json={"title": "Lamp", "dimensions_text": "30 x 30 x 150 cm"}).json()
    assert prod["ok"] and prod["object"]["dimensions_m"] == [0.3, 1.5, 0.3]
    glb = client.get(f"/api/plugins/roomsmith/projects/{pid}/export?format=glb")
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    js = client.get(f"/api/plugins/roomsmith/projects/{pid}/export?format=json")
    assert js.json()["scene"]["project"]["name"] == "Office"
    imp = client.post("/api/plugins/roomsmith/projects", json={"import": js.json(), "name": "Office copy"})
    assert imp.status_code == 201 and imp.json()["name"] == "Office copy"
    assert client.patch(f"/api/plugins/roomsmith/projects/{pid}", json={"name": "Office 2"}).json()["name"] == "Office 2"
    assert client.post(f"/api/plugins/roomsmith/projects/{pid}/activate").json()["active_project_id"] == pid
    lst = client.get("/api/plugins/roomsmith/projects").json()
    assert len(lst["projects"]) == 2
    assert client.delete(f"/api/plugins/roomsmith/projects/{pid}").json()["ok"]
    assert client.get(f"/api/plugins/roomsmith/projects/{pid}/head").status_code == 404


def test_photo_upload_and_fetch(client):
    bad = client.post("/api/plugins/roomsmith/photos", content=b"not an image")
    assert bad.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
    r = client.post("/api/plugins/roomsmith/photos", content=png, headers={"Content-Type": "image/png"})
    assert r.status_code == 201
    pid = r.json()["photo_id"]
    g = client.get(f"/api/plugins/roomsmith/photos/{pid}")
    assert g.status_code == 200 and g.content == png and g.headers["content-type"].startswith("image/png")
    assert client.get("/api/plugins/roomsmith/photos/nope").status_code == 404


def test_wait_long_poll_returns_immediately_when_newer(client):
    pid = client.post("/api/plugins/roomsmith/projects", json={"name": "W"}).json()["project_id"]
    r = client.get(f"/api/plugins/roomsmith/projects/{pid}/wait?after=0&timeout=1").json()
    assert r["changed"] is True and r["revision"] == 1
    r = client.get(f"/api/plugins/roomsmith/projects/{pid}/wait?after=1&timeout=0.6").json()
    assert r["changed"] is False and r["revision"] == 1
