import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "data" / "search_api.db"))
SESSION_TTL = 86400 * 7  # 7 days


def _ensure_db_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                usage_count INTEGER NOT NULL DEFAULT 0,
                last_used_at INTEGER,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name TEXT,
                engine TEXT NOT NULL,
                query TEXT NOT NULL,
                page INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            """
        )
        # 默认设置
        defaults = {
            "require_api_key": "1",
            "default_engine": "so_qq",
            "brave_api_key": "",
            "session_secret": secrets.token_hex(32),
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )


def _hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    actual = _hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def has_admin() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM admins").fetchone()
        return row["cnt"] > 0


def create_admin(username: str, password: str) -> bool:
    username = username.strip()
    if not username or len(password) < 6:
        raise ValueError("用户名不能为空且密码至少 6 位")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, _hash_password(password), int(time.time())),
        )
    return True


def verify_admin(username: str, password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM admins WHERE username = ?", (username.strip(),)
        ).fetchone()
        if not row:
            return False
        return _verify_password(password, row["password_hash"])


def update_admin_password(username: str, new_password: str):
    if len(new_password) < 6:
        raise ValueError("新密码至少 6 位")
    with get_conn() as conn:
        conn.execute(
            "UPDATE admins SET password_hash = ? WHERE username = ?",
            (_hash_password(new_password), username),
        )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def create_session_token(username: str) -> str:
    secret = get_setting("session_secret")
    exp = int(time.time()) + SESSION_TTL
    payload = f"{username}|{exp}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def verify_session_token(token: str) -> str | None:
    if not token:
        return None
    parts = token.split("|")
    if len(parts) != 3:
        return None
    username, exp_str, sig = parts
    try:
        exp = int(exp_str)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    secret = get_setting("session_secret")
    expected = hmac.new(
        secret.encode("utf-8"), f"{username}|{exp_str}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(sig, expected):
        return username
    return None


def list_api_keys() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, api_key, is_active, usage_count, last_used_at, created_at "
            "FROM api_keys ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def create_api_key(name: str) -> dict:
    name = name.strip() or "default"
    raw_key = "sk-" + secrets.token_urlsafe(24)
    now = int(time.time())
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (name, api_key, is_active, usage_count, created_at) "
            "VALUES (?, ?, 1, 0, ?)",
            (name, raw_key, now),
        )
        return {
            "id": cur.lastrowid,
            "name": name,
            "api_key": raw_key,
            "is_active": 1,
            "usage_count": 0,
            "last_used_at": None,
            "created_at": now,
        }


def toggle_api_key(key_id: int, is_active: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE api_keys SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, key_id),
        )


def delete_api_key(key_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))


def verify_api_key(token: str) -> str | None:
    """校验 API Key，有效则递增计数并返回 key_name，无效返回 None。"""
    if not token:
        return None
    env_key = os.environ.get("API_KEY", "").strip()
    if env_key and hmac.compare_digest(token, env_key):
        return "env-master-key"
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, is_active FROM api_keys WHERE api_key = ?", (token,)
        ).fetchone()
        if not row or not row["is_active"]:
            return None
        conn.execute(
            "UPDATE api_keys SET usage_count = usage_count + 1, last_used_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        return row["name"]


def log_search(key_name: str | None, engine: str, query: str, page: int):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO request_logs (key_name, engine, query, page, created_at) VALUES (?, ?, ?, ?, ?)",
            (key_name or "anonymous", engine, query[:200], page, now),
        )
        # 只保留最近 500 条日志，防止 SQLite 无限膨胀
        conn.execute(
            "DELETE FROM request_logs WHERE id NOT IN ("
            "SELECT id FROM request_logs ORDER BY id DESC LIMIT 500)"
        )


def get_recent_logs(limit: int = 30) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, key_name, engine, query, page, created_at "
            "FROM request_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total_keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        active_keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1").fetchone()[0]
        total_calls = conn.execute("SELECT COALESCE(SUM(usage_count), 0) FROM api_keys").fetchone()[0]
        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_calls": total_calls,
        }
