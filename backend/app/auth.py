import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request

from .db import connect, new_id, now


SESSION_COOKIE = "codezzn_session"
OAUTH_STATE_COOKIE = "codezzn_oauth_state"
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
        with connect(global_db=True) as db:
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
    with connect(global_db=True) as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not _password_matches(str(password or ""), row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确")
    return _public_user(row)


def create_session(user_id: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    timestamp, expires = now(), now() + SESSION_DAYS * 86400
    with connect(global_db=True) as db:
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
        with connect(global_db=True) as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_digest(token),))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")


def request_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    timestamp = now()
    token_hash = _digest(token)
    with connect(global_db=True) as db:
        row = db.execute(
            "SELECT u.*,s.last_seen_at AS session_last_seen_at FROM auth_sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>?", (token_hash, timestamp),
        ).fetchone()
        if row and row["session_last_seen_at"] <= timestamp - 60:
            db.execute(
                "UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=? AND last_seen_at<=?",
                (timestamp, token_hash, timestamp - 60),
            )
    return _public_user(row) if row else None


def github_configured() -> bool:
    return bool(os.getenv("CODEZZN_GITHUB_CLIENT_ID") and os.getenv("CODEZZN_GITHUB_CLIENT_SECRET"))


def github_authorize_url(next_path: str | None = None) -> tuple[str, str]:
    client_id = os.getenv("CODEZZN_GITHUB_CLIENT_ID")
    if not client_id or not os.getenv("CODEZZN_GITHUB_CLIENT_SECRET"):
        raise HTTPException(503, "GitHub 登录尚未配置，请设置 CODEZZN_GITHUB_CLIENT_ID 和 CODEZZN_GITHUB_CLIENT_SECRET")
    state = secrets.token_urlsafe(32)
    timestamp = now()
    with connect(global_db=True) as db:
        db.execute("DELETE FROM oauth_states WHERE expires_at<=?", (timestamp,))
        db.execute(
            "INSERT INTO oauth_states(state_hash,provider,next_path,created_at,expires_at) VALUES(?,?,?,?,?)",
            (_digest(state), "github", _safe_next(next_path), timestamp, timestamp + 600),
        )
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id, "redirect_uri": _github_redirect_uri(), "scope": "read:user user:email",
        "state": state, "prompt": "select_account",
    })
    return url, state


def _github_redirect_uri() -> str:
    public_url = os.getenv("CODEZZN_PUBLIC_URL", "http://127.0.0.1:8080").rstrip("/")
    return public_url + "/api/auth/github/callback"


async def github_callback(code: str, state: str) -> tuple[dict, str]:
    timestamp = now()
    with connect(global_db=True) as db:
        saved = db.execute(
            "SELECT * FROM oauth_states WHERE state_hash=? AND provider='github' AND expires_at>?",
            (_digest(state), timestamp),
        ).fetchone()
        db.execute("DELETE FROM oauth_states WHERE state_hash=?", (_digest(state),))
    if not saved:
        raise HTTPException(400, "GitHub 登录状态已失效，请重新尝试")
    # Keep the proxy scoped to GitHub: local RAGFlow/MCP traffic must not
    # accidentally leave the LAN through a host-wide HTTPS proxy.
    proxy = os.getenv("CODEZZN_GITHUB_PROXY_URL") or None
    try:
        transport = httpx.AsyncHTTPTransport(retries=1, proxy=proxy)
    except (ImportError, ValueError) as exc:
        raise HTTPException(502, "GitHub 代理配置无效") from exc
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5), follow_redirects=True, transport=transport,
        ) as client:
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
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "GitHub 响应超时，请重新登录") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "GitHub 接口暂不可用，请重新登录") from exc
    if not email:
        raise HTTPException(400, "GitHub 账号没有可用的已验证邮箱")
    github_id = str(profile["id"])
    email = email.strip().lower()
    name = str(profile.get("name") or profile.get("login") or email.split("@", 1)[0])[:80]
    avatar_url = str(profile.get("avatar_url") or "")[:1000]
    try:
        with connect(global_db=True) as db:
            linked = db.execute("SELECT * FROM users WHERE github_id=?", (github_id,)).fetchone()
            email_owner = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if linked:
                # GitHub ID is the stable identity. A changed email must not steal
                # an address already owned by a different local account.
                user_id = linked["id"]
                safe_email = linked["email"] if email_owner and email_owner["id"] != user_id else email
                db.execute("UPDATE users SET email=?,name=?,avatar_url=?,updated_at=? WHERE id=?", (safe_email, name, avatar_url, timestamp, user_id))
            elif email_owner:
                if email_owner["github_id"]:
                    raise HTTPException(409, "此邮箱已绑定其他 GitHub 账号")
                user_id = email_owner["id"]
                db.execute("UPDATE users SET name=?,avatar_url=?,github_id=?,updated_at=? WHERE id=?", (name, avatar_url, github_id, timestamp, user_id))
            else:
                user_id = new_id("usr")
                db.execute(
                    "INSERT INTO users(id,email,name,password_hash,avatar_url,github_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, email, name, None, avatar_url, github_id, timestamp, timestamp),
                )
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "GitHub 账号与现有用户资料冲突") from exc
    return _public_user(row), _safe_next(saved["next_path"])
