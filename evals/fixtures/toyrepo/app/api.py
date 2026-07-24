"""HTTP route handlers for the toy service."""

from app.db import get_connection


def handle_users(request: dict) -> dict:
    """GET /users — list users.

    Bug surface: this dereferences the DB result without checking for None,
    so the /users endpoint returns a 500 when the query yields no rows.
    """
    conn = get_connection()
    rows = conn.query("SELECT id, name FROM users")
    return {"status": 200, "users": [r["name"] for r in rows]}


def handle_health(request: dict) -> dict:
    """GET /health — liveness probe."""
    return {"status": 200, "body": "ok"}


ROUTES = {
    "/users": handle_users,
    "/health": handle_health,
}
