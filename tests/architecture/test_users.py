import sqlite3

from fastapi.testclient import TestClient

from engine import AgentEngine
from llm import ModelClient
from module3_host.api.app import create_app
from module3_host.api.service import initial_game
from module3_host.storage import Repository


def test_register_login_logout_profile_and_password(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(create_app(tmp_path / "users.sqlite3", AgentEngine(ModelClient()))) as client:
        csrf = client.get("/api/state").json()["csrf"]
        client.headers["X-CSRF-Token"] = csrf
        initial_cookie = client.cookies.get("soup_session")
        assert client.post("/api/new", json={"play_mode": "solo"}).status_code == 401
        assert client.patch("/api/users/me", json={"display_name": "未登录玩家"}).status_code == 401

        registered = client.post("/api/users/register", json={
            "email": "PLAYER@Example.COM", "password": "first-password", "display_name": "玩家甲"
        })
        assert registered.status_code == 200, registered.text
        assert registered.json()["user"]["email"] == "player@example.com"
        assert "password" not in str(registered.json())
        assert client.cookies.get("soup_session") != initial_cookie
        with TestClient(client.app) as stale:
            stale.cookies.set("soup_session", initial_cookie)
            assert stale.get("/api/users/me").json()["email"] is None
        with TestClient(client.app) as duplicate:
            duplicate.headers["X-CSRF-Token"] = duplicate.get("/api/state").json()["csrf"]
            assert duplicate.post("/api/users/register", json={
                "email": "player@example.com", "password": "another-password", "display_name": "其他玩家"
            }).status_code == 409
        client.headers["X-CSRF-Token"] = registered.json()["csrf"]
        game_id = client.post("/api/new", json={"play_mode": "solo"}).json()["game_id"]
        assert client.patch("/api/users/me", json={"display_name": "玩家乙"}).json()["display_name"] == "玩家乙"
        assert client.post("/api/users/register", json={
            "email": "other@example.com", "password": "other-password", "display_name": "玩家丙"
        }).status_code == 409

        assert client.post("/api/users/password", json={
            "current_password": "wrong-password", "new_password": "second-password"
        }).status_code == 401
        assert client.post("/api/users/password", json={
            "current_password": "first-password", "new_password": "second-password"
        }).status_code == 200

        logged_out = client.post("/api/users/logout", json={})
        assert logged_out.status_code == 200
        assert logged_out.json()["user"]["email"] is None
        assert client.get("/api/state").json()["status"] == "idle"
        client.headers["X-CSRF-Token"] = logged_out.json()["csrf"]
        assert client.post("/api/new", json={}).status_code == 401
        assert client.post("/api/users/login", json={
            "email": "player@example.com", "password": "first-password"
        }).status_code == 401
        logged_in = client.post("/api/users/login", json={
            "email": "PLAYER@example.com", "password": "second-password"
        })
        assert logged_in.status_code == 200, logged_in.text
        assert logged_in.json()["user"]["display_name"] == "玩家乙"
        assert client.get("/api/state").json()["game_id"] == game_id


def test_account_validation_and_csrf(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(create_app(tmp_path / "users.sqlite3", AgentEngine(ModelClient()))) as client:
        csrf = client.get("/api/state").json()["csrf"]
        data = {"email": "test@example.com", "password": "long-enough", "display_name": "玩家"}
        assert client.post("/api/users/register", json=data).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert client.post("/api/users/register", json={**data, "password": "short"}).status_code == 422
        assert client.post("/api/users/register", json={**data, "email": "invalid"}).status_code == 422
        assert client.post("/api/users/register", json={**data, "role": "admin"}).status_code == 422
        assert client.get("/api/users/me").json()["email"] is None


def test_legacy_anonymous_game_is_not_exposed(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(create_app(tmp_path / "legacy.sqlite3", AgentEngine(ModelClient()))) as client:
        client.get("/api/state")
        repo = client.app.state.repository
        session, _ = repo.session(client.cookies.get("soup_session"))
        game = initial_game()
        game.update(puzzle=repo.puzzles(demo=True)[0], status="playing")
        repo.start_game(session["id"], game, None)
        state = client.get("/api/state").json()
        assert state["status"] == "idle"
        assert state["puzzle"] is None


def test_existing_anonymous_database_is_migrated(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at REAL NOT NULL)")
        db.execute("INSERT INTO users VALUES('old-user','旧玩家',0)")
    repo = Repository(path)
    assert repo.user("old-user") == {"id": "old-user", "display_name": "旧玩家", "email": None,
                                     "role": "player", "is_active": 1}
    assert repo.session()[0]["user_id"] != "old-user"
    assert [row[0] for row in sqlite3.connect(path).execute("SELECT version FROM schema_version")] == [3]


def test_admin_can_manage_players_but_cannot_play(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    path = tmp_path / "admin.sqlite3"
    repo = Repository(path)
    repo.create_admin("admin@example.com", "admin-password", "管理员")
    app = create_app(path, AgentEngine(ModelClient()))
    with TestClient(app) as player, TestClient(app) as admin:
        player.headers["X-CSRF-Token"] = player.get("/api/state").json()["csrf"]
        registered = player.post("/api/users/register", json={
            "email": "player@example.com", "password": "player-password", "display_name": "玩家甲"
        }).json()
        player.headers["X-CSRF-Token"] = registered["csrf"]
        uid = registered["user"]["id"]
        assert player.get("/api/admin/users").status_code == 403
        assert player.post("/api/new", json={}).status_code == 200

        admin.headers["X-CSRF-Token"] = admin.get("/api/state").json()["csrf"]
        logged_in = admin.post("/api/users/login", json={
            "email": "admin@example.com", "password": "admin-password"
        }).json()
        admin.headers["X-CSRF-Token"] = logged_in["csrf"]
        assert logged_in["user"]["role"] == "admin"
        assert admin.post("/api/new", json={}).status_code == 403
        found = admin.get("/api/admin/users?q=player").json()
        assert found["total"] == 1
        assert found["users"][0]["game_count"] == 1
        assert "password_hash" not in str(found)
        assert admin.patch(f"/api/admin/users/{uid}", json={"display_name": "玩家乙"}).json()["display_name"] == "玩家乙"
        assert admin.patch(f"/api/admin/users/{uid}", json={"role": "admin"}).status_code == 422
        assert admin.patch(f"/api/admin/users/{uid}", json={"is_active": False}).json()["is_active"] == 0
        assert player.get("/api/users/me").json()["email"] is None
        assert player.post("/api/new", json={}).status_code == 403  # stale CSRF after session invalidation
        player.headers["X-CSRF-Token"] = player.get("/api/state").json()["csrf"]
        assert player.post("/api/users/login", json={
            "email": "player@example.com", "password": "player-password"
        }).status_code == 403
        admin.patch(f"/api/admin/users/{uid}", json={"is_active": True})
        assert player.post("/api/users/login", json={
            "email": "player@example.com", "password": "player-password"
        }).status_code == 200
