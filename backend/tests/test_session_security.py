from pathlib import Path

from fastapi.testclient import TestClient

from backend import database
from backend.api import server


def _auth_header(user_id: str) -> dict[str, str]:
    token = server._jwt_sign({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_session_history_requires_owner(tmp_path: Path):
    db_path = tmp_path / "test_voice_assistant.db"
    old_db_path = database.DB_PATH
    database.DB_PATH = str(db_path)
    try:
        database.init_db()
        owner_id = database.create_user("owner", "pw")
        other_id = database.create_user("other", "pw")
        assert owner_id is not None
        assert other_id is not None

        session_id = database.create_session(owner_id)
        database.add_message(session_id, "user", "hello")

        client = TestClient(server.app)

        ok_resp = client.get(
            f"/api/sessions/{session_id}/history",
            headers=_auth_header(owner_id),
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json()["messages"][0]["content"] == "hello"

        forbidden_resp = client.get(
            f"/api/sessions/{session_id}/history",
            headers=_auth_header(other_id),
        )
        assert forbidden_resp.status_code == 200
        assert forbidden_resp.json() == {"ok": False, "error": "session_forbidden"}
    finally:
        database.DB_PATH = old_db_path


def test_session_history_allows_anonymous_owner_via_user_id(tmp_path: Path):
    db_path = tmp_path / "test_voice_assistant.db"
    old_db_path = database.DB_PATH
    database.DB_PATH = str(db_path)
    try:
        database.init_db()
        session_id = database.create_session("anon-user")
        database.add_message(session_id, "assistant", "welcome")

        client = TestClient(server.app)
        ok_resp = client.get(
            f"/api/sessions/{session_id}/history",
            params={"user_id": "anon-user"},
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json()["messages"][0]["content"] == "welcome"

        forbidden_resp = client.get(
            f"/api/sessions/{session_id}/history",
            params={"user_id": "other-user"},
        )
        assert forbidden_resp.status_code == 200
        assert forbidden_resp.json() == {"ok": False, "error": "session_forbidden"}
    finally:
        database.DB_PATH = old_db_path


def test_delete_session_rejects_non_owner(tmp_path: Path):
    db_path = tmp_path / "test_voice_assistant.db"
    old_db_path = database.DB_PATH
    database.DB_PATH = str(db_path)
    try:
        database.init_db()
        owner_id = database.create_user("owner", "pw")
        other_id = database.create_user("other", "pw")
        assert owner_id is not None
        assert other_id is not None

        session_id = database.create_session(owner_id)

        client = TestClient(server.app)
        forbidden_resp = client.delete(
            f"/api/sessions/{session_id}",
            headers=_auth_header(other_id),
        )
        assert forbidden_resp.status_code == 200
        assert forbidden_resp.json() == {"ok": False, "error": "session_not_found"}
        assert database.get_session_owner(session_id) == owner_id

        ok_resp = client.delete(
            f"/api/sessions/{session_id}",
            headers=_auth_header(owner_id),
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json() == {"ok": True}
        assert database.get_session_owner(session_id) is None
    finally:
        database.DB_PATH = old_db_path
