"""What a reviewer checks first: where the plugin connects, where it writes,
and what happens when the model sends nonsense."""

import gzip
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rs_core import product_fetch as pf  # noqa: E402

PRIVATE = [
    "http://localhost/x", "http://localhost./x", "http://127.0.0.1:8080/admin", "http://127.0.0.2/", "http://0.0.0.0/",
    "http://2130706433/", "http://0x7f.1/", "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://[fd00::1]/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://100.100.100.100/", "http://metadata.google.internal/", "http://printer.local/", "file:///etc/passwd", "ftp://x/y", "http://[bad",
]


@pytest.mark.parametrize("url", PRIVATE)
def test_private_and_malformed_urls_are_refused_without_a_request(url):
    r = pf.fetch_product(url, _get=lambda *a, **k: pytest.fail("no request may be made"))
    assert r["ok"] is False and r["error"]["code"] == "bad_url"


def test_public_names_that_resolve_to_private_addresses_are_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(pf.FetchError) as e:
        pf.http_get("http://looks-public.example.com/")
    assert e.value.code == "bad_url"


def test_redirects_are_checked_like_first_requests():
    handler = pf._PublicRedirects()
    with pytest.raises(pf.FetchError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://169.254.169.254/")


def test_gzip_is_capped_and_truncation_is_not_an_error():
    with pytest.raises(pf.FetchError) as e:
        pf._gunzip_capped(gzip.compress(b"0" * (pf.MAX_BYTES + 1024)))
    assert e.value.code == "too_large"
    assert pf._gunzip_capped(gzip.compress(b"hello")) == b"hello"


@pytest.fixture
def call(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    from rs_agent import tools

    tools.reset_service()
    table = {"new_room": tools.new_room, "apply": tools.apply, "inspect": tools.inspect, "history": tools.history, "export": tools.export, "read_product": tools.read_product, "check": tools.check}
    yield lambda tool, **args: json.loads(table[tool](args))
    tools.reset_service()


def test_bad_arguments_come_back_as_errors_the_model_can_read(call):
    assert call("new_room", width_m="four", depth_m=5)["error"]["code"] == "invalid_value"
    assert call("new_room", name="Study", width_m="4", depth_m="5")["ok"]
    assert call("history", action="undo", steps="two")["ok"] in (True, False)
    r = call("apply", operations=[{"op": "add_object", "name": "Desk", "category": "desk"}])
    assert r["ok"]
    r = call("apply", operations=[{"op": "move_object", "id": "ob1", "place": "against the left wall"}])
    assert r["ok"] is False and r["error"]["code"] == "invalid_value"
    assert call("read_product", url="http://[bad")["error"]["code"] == "bad_url"
    for r in (call("apply", operations="nope"), call("check", question="fits_at", place="here"), call("history", limit="many")):
        assert "trace" not in json.dumps(r)


def test_operations_sent_as_a_json_string_are_accepted(call):
    call("new_room", name="Study", width_m=4, depth_m=5)
    r = call("apply", operations=json.dumps([{"op": "add_object", "name": "Chair", "category": "chair"}]))
    assert r["ok"], r


def test_the_model_cannot_replay_or_choose_a_command_id(call):
    call("new_room", name="Study", width_m=4, depth_m=5)
    a = call("apply", command_id="same", operations=[{"op": "add_object", "name": "Chair", "category": "chair"}])
    b = call("apply", command_id="same", operations=[{"op": "add_object", "name": "Lamp", "category": "lamp_floor"}])
    assert a["ok"] and b["ok"] and not b.get("replayed")
    assert len(call("inspect")["objects"]) == 2


def test_exports_stay_inside_the_plugin_data_folder(call, tmp_path):
    call("new_room", name="Study", width_m=4, depth_m=5)
    r = call("export", format="glb", out_dir="/tmp/somewhere-else")
    assert r["ok"] and Path(r["path"]).parent == tmp_path / "exports"


def test_full_inspect_never_carries_embedded_images(call):
    from rs_agent import tools

    call("new_room", name="Study", width_m=4, depth_m=5)
    svc = tools.get_service()
    r = svc.add_product(None, title="Sofa", dimensions_m=[2.0, 0.8, 0.9], actor="agent")
    assert r["ok"], r
    scene, rev = svc.store.get_scene(svc.active_project_id())
    scene["objects"][0]["product"]["image_data"] = "data:image/jpeg;base64," + "A" * 50_000
    svc.store.commit_revision(svc.active_project_id(), rev, scene, "system", "test", [], history_mode="none")
    full = call("inspect", detail="full")
    assert full["ok"] and "image_data" not in json.dumps(full) and len(json.dumps(full)) < 20_000
