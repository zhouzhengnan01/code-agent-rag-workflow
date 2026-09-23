import base64
import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request

from .db import connect, new_id, now


SESSION_COOKIE = "codezzn_session"
SESSION_DAYS = max(1, int(os.getenv("CODEZZN_SESSION_DAYS", "14")))
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def _password_matches(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.urlsafe_b64decode(salt.encode()),
            n=int(n), r=int(r), p=int(p), dklen=32,
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected.encode()))
    except (ValueError, TypeError):
        return False


def _public_user(row) -> dict:
    return {
        "id": row["id"], "email": row["email"], "name": row["name"],
        "avatar_url": row["avatar_url"], "provider": "github" if row["github_id"] else "local",
    }


def _safe_next(value: str | None) -> str:
    value = str(value or "/workbench.html")
    return value if value.startswith("/") and not value.startswith("//") else "/workbench.html"


def register_user(name: str, email: str, password: str) -> dict:
    name, email = str(name or "").strip(), str(email or "").strip().lower()
    password = str(password or "")
    if len(name) < 2 or len(name) > 80:
        raise HTTPException(400, "姓名长度应为 2-80 个字符")
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        raise HTTPException(400, "请输入有效的邮箱地址")
    if len(password) < 10 or len(password) > 200:
        raise HTTPException(400, "密码至少需要 10 个字符")
    timestamp = now()
    try:
        with connect() as db:
            user_id = new_id("usr")
            db.execute(
                "INSERT INTO users(id,email,name,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (user_id, email, name, _password_hash(password), timestamp, timestamp),
            )
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except Exception as exc:
        if "UNIQUE constraint failed: users.email" in str(exc):
            raise HTTPException(409, "该邮箱已注册") from exc
        raise
    return _public_user(row)


def login_user(email: str, password: str) -> dict:
    email = str(email or "").strip().lower()
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not _password_matches(str(password or ""), row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确")
    return _public_user(row)


def create_session(user_id: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    timestamp, expires = now(), now() + SESSION_DAYS * 86400
    with connect() as db:
        db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (timestamp,))
        db.execute(
            "INSERT INTO auth_sessions(id,user_id,token_hash,expires_at,created_at,last_seen_at) VALUES(?,?,?,?,?,?)",
            (new_id("ses"), user_id, _digest(token), expires, timestamp, timestamp),
        )
    return token, expires


def set_session_cookie(response, token: str, expires_at: int):
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max(0, expires_at - now()), httponly=True,
        secure=os.getenv("CODEZZN_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax", path="/",
    )


def clear_session(request: Request, response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with connect() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_digest(token),))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")


def request_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    timestamp = now()
    with connect() as db:
        row = db.execute(
            "SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>?", (_digest(token), timestamp),
        ).fetchone()
        if row:
            db.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (timestamp, _digest(token)))
    return _public_user(row) if row else None


def github_configured() -> bool:
    return bool(os.getenv("CODEZZN_GITHUB_CLIENT_ID") and os.getenv("CODEZZN_GITHUB_CLIENT_SECRET"))


def github_authorize_url(next_path: str | None = None) -> str:
    client_id = os.getenv("CODEZZN_GITHUB_CLIENT_ID")
    if not client_id or not os.getenv("CODEZZN_GITHUB_CLIENT_SECRET"):
        raise HTTPException(503, "GitHub 登录尚未配置，请设置 CODEZZN_GITHUB_CLIENT_ID 和 CODEZZN_GITHUB_CLIENT_SECRET")
    state = secrets.token_urlsafe(32)
    timestamp = now()
    with connect() as db:
        db.execute("DELETE FROM oauth_states WHERE expires_at<=?", (timestamp,))
        db.execute(
            "INSERT INTO oauth_states(state_hash,provider,next_path,created_at,expires_at) VALUES(?,?,?,?,?)",
            (_digest(state), "github", _safe_next(next_path), timestamp, timestamp + 600),
        )
    return "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id, "redirect_uri": _github_redirect_uri(), "scope": "read:user user:email", "state": state,
    })


def _github_redirect_uri() -> str:
    public_url = os.getenv("CODEZZN_PUBLIC_URL", "http://127.0.0.1:8080").rstrip("/")
    return public_url + "/api/auth/github/callback"


async def github_callback(code: str, state: str) -> tuple[dict, str]:
    timestamp = now()
    with connect() as db:
        saved = db.execute(
            "SELECT * FROM oauth_states WHERE state_hash=? AND provider='github' AND expires_at>?",
            (_digest(state), timestamp),
        ).fetchone()
        db.execute("DELETE FROM oauth_states WHERE state_hash=?", (_digest(state),))
    if not saved:
        raise HTTPException(400, "GitHub 登录状态已失效，请重新尝试")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": os.getenv("CODEZZN_GITHUB_CLIENT_ID"),
                "client_secret": os.getenv("CODEZZN_GITHUB_CLIENT_SECRET"),
                "code": code, "redirect_uri": _github_redirect_uri(),
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(400, "GitHub 未返回访问令牌")
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        profile_response = await client.get("https://api.github.com/user", headers=headers)
        profile_response.raise_for_status()
        profile = profile_response.json()
        email = profile.get("email")
        if not email:
            emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
            emails_response.raise_for_status()
            emails = emails_response.json()
            preferred = next((item for item in emails if item.get("primary") and item.get("verified")), None)
            preferred = preferred or next((item for item in emails if item.get("verified")), None)
            email = preferred.get("email") if preferred else None
    if not email:
        raise HTTPException(400, "GitHub 账号没有可用的已验证邮箱")
    github_id = str(profile["id"])
    email = email.strip().lower()
    name = str(profile.get("name") or profile.get("login") or email.split("@", 1)[0])[:80]
    avatar_url = str(profile.get("avatar_url") or "")[:1000]
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE github_id=? OR email=? ORDER BY github_id=? DESC LIMIT 1", (github_id, email, github_id)).fetchone()
        if row:
            db.execute("UPDATE users SET email=?,name=?,avatar_url=?,github_id=?,updated_at=? WHERE id=?", (email, name, avatar_url, github_id, timestamp, row["id"]))
            user_id = row["id"]
        else:
            user_id = new_id("usr")
            db.execute(
                "INSERT INTO users(id,email,name,password_hash,avatar_url,github_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (user_id, email, name, None, avatar_url, github_id, timestamp, timestamp),
            )
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _public_user(row), _safe_next(saved["next_path"])
