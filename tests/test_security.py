import os

import pytest

import server


@pytest.fixture
def client():
    for f in (server._PEOPLE_FILE, server._THROTTLE_FILE):
        if os.path.exists(f):
            os.remove(f)
    return server.app.test_client()


def make(role, login, pin="123456"):
    people = server._load_people()
    people["users"].append({"id": "u-" + login, "name": login, "login": login, "role": role, "active": True,
                            "pin_hash": server._hash_pin(pin), "permissions": {}})
    server._save_people(people)


def login(c, name, pin="123456"):
    return c.post("/api/auth/login", json={"login": name, "pin": pin})


ROUTES = sorted({(r.rule, m) for r in server.app.url_map.iter_rules() for m in r.methods - {"HEAD", "OPTIONS"}
                 if r.rule.startswith("/api/") and not r.rule.startswith("/api/auth/")})


def test_every_api_route_refuses_anonymous(client):
    make("admin", "boss")
    for rule, method in ROUTES:
        path = rule.replace("<int:", "<").replace("<path:", "<")
        path = __import__("re").sub(r"<[^>]+>", "1", path)
        assert client.open(path, method=method, json={}).status_code == 401, (method, path)


def test_first_admin_needs_token(client):
    r = client.post("/api/people", json={"name": "A", "pin": "123456"})
    assert r.status_code == 403
    r = client.post("/api/people", json={"name": "A", "pin": "123456", "setup_token": server._setup_token()})
    assert r.status_code == 201


def test_roles(client):
    make("admin", "boss")
    make("manager", "mgr")
    make("staff", "bob")
    assert login(client, "bob").status_code == 200
    assert client.get("/api/venue/overview").status_code == 200
    assert client.get("/api/venue/reports/variance").status_code == 403
    assert client.post("/api/hard-reset").status_code == 403
    assert client.get("/api/people").status_code == 403
    login(client, "mgr")
    assert client.get("/api/venue/reports/variance").status_code == 200
    assert client.get("/api/people").status_code == 403


def test_lockout_then_right_pin_refused(client):
    make("admin", "boss")
    for _ in range(5):
        assert login(client, "boss", "000000").status_code == 401
    assert login(client, "boss").status_code == 429
    assert login(client, "boss").status_code == 429


def test_legacy_hash_migrates(client):
    salt = "abc"
    people = server._load_people()
    people["users"].append({"id": "o", "name": "Old", "login": "old", "role": "admin", "active": True,
                            "pin_hash": server._legacy_digest("654321", salt), "pin_salt": salt})
    server._save_people(people)
    assert server._migrate_pin_hashes() == 1
    assert server._find_user(server._load_people(), login="old")["pin_hash"].startswith("wrapped:scrypt")
    assert login(client, "old", "654321").status_code == 200
    u = server._find_user(server._load_people(), login="old")
    assert u["pin_hash"].startswith("scrypt") and "pin_salt" not in u


def test_cross_origin_post_refused(client):
    make("admin", "boss")
    login(client, "boss")
    r = client.post("/api/hard-reset", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert "Access-Control-Allow-Origin" not in r.headers


def test_bundle_round_trip_and_refuses_existing_stock(tmp_path, monkeypatch):
    import manage

    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "venue.sqlite").write_bytes(b"")
    (src / "people.json").write_text("{}")
    (src / "session_secret.txt").write_text("secret")
    bundle = str(tmp_path / "b.txt")
    monkeypatch.setattr(manage, "DATA", str(src))
    manage.export_data(bundle, "good-password")
    monkeypatch.setattr(manage, "DATA", str(dst))
    assert manage.import_data(bundle, "bad-password") == 4
    assert not dst.exists()
    assert manage.import_data(bundle, "good-password") == 0
    assert (dst / "people.json").exists() and not (dst / "session_secret.txt").exists()
    assert manage.import_data(bundle, "good-password") == 3
