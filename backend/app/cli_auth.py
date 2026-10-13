"""One-shot device consent and revocable, account-scoped CLI credentials."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .db import connect, new_id, now


router = APIRouter()
DEVICE_SECONDS = 600
POLL_SECONDS = 3
TOKEN_SECONDS = 30 * 86400
USER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
WEB = Path(__file__).resolve().parents[2] / "web"
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def init_cli_auth_tables():
    # Authentication always lives in the shared identity DB, never a tenant DB.
    with connect(global_db=True) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS cli_devices (
                device_hash TEXT PRIMARY KEY, user_code_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                user_id TEXT, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                last_poll_at INTEGER, redeemed_at INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_cli_devices_expiry ON cli_devices(expires_at);
            CREATE TABLE IF NOT EXISTS cli_tokens (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_cli_tokens_user ON cli_tokens(user_id, expires_at);
            CREATE TABLE IF NOT EXISTS cli_rate_limits (
                bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL
            );
        """)


def _response(body, status=200, headers=None):
    return JSONResponse(body, status_code=status, headers={**NO_STORE, **(headers or {})})


def _error(error, status, retry_after=None):
    body = {"error": error}
    headers = {}
    if retry_after is not None:
        body["interval"] = retry_after
        headers["Retry-After"] = str(retry_after)
    return _response(body, status, headers)


def _cleanup(db, timestamp):
    # Keep device tombstones for a day so expired polling has a useful outcome.
    db.execute("DELETE FROM cli_devices WHERE expires_at<=?", (timestamp - 86400,))
    db.execute("DELETE FROM cli_tokens WHERE expires_at<=? OR revoked_at<=?", (timestamp, timestamp - 86400))
    db.execute("DELETE FROM cli_rate_limits WHERE window_start<=?", (timestamp - 600,))


def _rate_allowed(db, request, action, timestamp, maximum):
    # Ignore caller-controlled forwarding headers: they cannot bypass throttles.
    address = request.client.host if request.client else "unknown"
    bucket = action + ":" + _digest(address)
    saved = db.execute("SELECT * FROM cli_rate_limits WHERE bucket=?", (bucket,)).fetchone()
    if saved and timestamp - saved["window_start"] < 600:
        if saved["attempts"] >= maximum:
            return False
        db.execute("UPDATE cli_rate_limits SET attempts=attempts+1 WHERE bucket=?", (bucket,))
    else:
        if not saved and db.execute("SELECT COUNT(*) FROM cli_rate_limits").fetchone()[0] >= 20000:
            return False
        db.execute("INSERT OR REPLACE INTO cli_rate_limits VALUES(?,?,1)", (bucket, timestamp))
    return True


def _public_url(request):
    configured = os.getenv("CODEZZN_PUBLIC_URL", "").strip()
    value = (configured or str(request.base_url)).rstrip("/")
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise HTTPException(503, "CODEZZN_PUBLIC_URL 地址无效") from exc
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise HTTPException(503, "CODEZZN_PUBLIC_URL 必须是有效的 HTTP 或 HTTPS 站点地址")
    return value


def _origin(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


def _user_code(value):
    if not isinstance(value, str) or len(value) > 20:
        raise HTTPException(400, "授权码格式无效")
    code = value.strip().upper().replace("-", "")
    if len(code) != 10 or any(letter not in USER_ALPHABET for letter in code):
        raise HTTPException(400, "授权码格式无效")
    return code


def _cookie_user(request):
    # Explicitly bypass request_user: admin keys and CLI bearer tokens are not consent.
    from .auth import SESSION_COOKIE, _public_user
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or len(token) > 200:
        raise HTTPException(401, "请先在浏览器登录，再确认 CLI 授权")
    with connect(global_db=True) as db:
        row = db.execute(
            "SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>?", (_digest(token), now()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "浏览器登录已过期，请重新登录")
    return _public_user(row), token


def _csrf_token(cookie, code):
    return hmac.new(cookie.encode(), ("cli-consent:" + code).encode(), hashlib.sha256).hexdigest()


def _require_origin(request):
    origin = request.headers.get("origin", "")
    # Compare normalized origins to support ordinary/default ports without accepting paths.
    expected = _origin(_public_url(request))
    if not origin or _origin(origin) != expected:
        raise HTTPException(403, "授权确认必须来自本站浏览器页面")
    if request.headers.get("sec-fetch-site", "") == "cross-site":
        raise HTTPException(403, "禁止跨站授权请求")


def _bearer(request):
    raw = request.headers.get("authorization")
    if raw is None:
        return None
    parts = raw.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not re.fullmatch(r"czz_cli_[A-Za-z0-9_-]{43}", parts[1]):
        raise HTTPException(401, "CLI 凭据无效", headers={"WWW-Authenticate": "Bearer"})
    return parts[1]


def _token_row(request):
    token = _bearer(request)
    if token is None:
        return None
    with connect(global_db=True) as db:
        row = db.execute(
            "SELECT u.*,t.expires_at AS cli_expires_at,t.id AS cli_token_id "
            "FROM cli_tokens t JOIN users u ON u.id=t.user_id "
            "WHERE t.token_hash=? AND t.expires_at>? AND t.revoked_at IS NULL",
            (_digest(token), now()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "CLI 登录已过期或已撤销", headers={"WWW-Authenticate": "Bearer"})
    return row


def resolve_cli_user(request):
    """Read-only identity resolution; invalid explicit credentials never fall back."""
    from .auth import _public_user
    row = _token_row(request)
    return _public_user(row) if row else None


@router.get("/cli/authorize")
def authorize_page():
    return FileResponse(WEB / "cli-authorize.html", headers={
        **NO_STORE, "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    })


@router.post("/api/auth/cli/device")
def start_device(request: Request, payload: dict = Body(...)):
    name = payload.get("name", "Codezzn CLI")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
        raise HTTPException(400, "CLI 名称长度应为 1–100 个字符")
    base_url = _public_url(request)
    if _origin(str(request.base_url)) != _origin(base_url):
        return _response({"error": "server_url_mismatch", "canonical_server": base_url,
                          "detail": "请使用配置的公共地址作为 --server：" + base_url}, 409)
    timestamp = now()
    with connect(global_db=True) as db:
        db.execute("BEGIN IMMEDIATE")
        _cleanup(db, timestamp)
        if not _rate_allowed(db, request, "device", timestamp, 10):
            return _error("rate_limited", 429, 60)
        if db.execute("SELECT COUNT(*) FROM cli_devices WHERE expires_at>?", (timestamp,)).fetchone()[0] >= 10000:
            return _error("temporarily_unavailable", 503, 60)
        for _ in range(5):
            device = secrets.token_urlsafe(32)
            code = "".join(secrets.choice(USER_ALPHABET) for _ in range(10))
            try:
                db.execute(
                    "INSERT INTO cli_devices(device_hash,user_code_hash,name,created_at,expires_at) VALUES(?,?,?,?,?)",
                    (_digest(device), _digest(code), name.strip(), timestamp, timestamp + DEVICE_SECONDS),
                )
                break
            except sqlite3.IntegrityError:
                continue
        else:
            return _error("temporarily_unavailable", 503)
    display_code = code[:5] + "-" + code[5:]
    return _response({
        "device_code": device, "user_code": display_code,
        "verification_uri": base_url + "/cli/authorize",
        "verification_uri_complete": base_url + "/cli/authorize?" + urlencode({"user_code": display_code}),
        "expires_in": DEVICE_SECONDS, "interval": POLL_SECONDS,
    })


@router.get("/api/auth/cli/device-info")
def device_info(request: Request, user_code: str):
    user, cookie = _cookie_user(request)
    code = _user_code(user_code)
    timestamp = now()
    with connect(global_db=True) as db:
        db.execute("BEGIN IMMEDIATE")
        _cleanup(db, timestamp)
        if not _rate_allowed(db, request, "consent", timestamp, 60):
            return _error("rate_limited", 429, 60)
        row = db.execute("SELECT * FROM cli_devices WHERE user_code_hash=?", (_digest(code),)).fetchone()
    if not row:
        return _error("invalid_user_code", 404)
    if row["expires_at"] <= timestamp:
        return _error("expired_token", 410)
    if row["status"] != "pending":
        return _error("already_processed", 409)
    return _response({"name": row["name"], "expires_at": row["expires_at"], "user": user,
                      "csrf_token": _csrf_token(cookie, code)})


@router.post("/api/auth/cli/approve")
def approve_device(request: Request, payload: dict = Body(...)):
    user, cookie = _cookie_user(request)
    _require_origin(request)
    code = _user_code(payload.get("user_code"))
    supplied = request.headers.get("x-cli-csrf", "")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(supplied, _csrf_token(cookie, code)):
        raise HTTPException(403, "授权确认状态无效，请刷新页面")
    decision = payload.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(400, "decision 必须是 approved 或 denied")
    timestamp = now()
    with connect(global_db=True) as db:
        db.execute("BEGIN IMMEDIATE")
        _cleanup(db, timestamp)
        if not _rate_allowed(db, request, "approve", timestamp, 60):
            return _error("rate_limited", 429, 60)
        row = db.execute("SELECT * FROM cli_devices WHERE user_code_hash=?", (_digest(code),)).fetchone()
        if not row:
            return _error("invalid_user_code", 404)
        if row["expires_at"] <= timestamp:
            return _error("expired_token", 410)
        if row["status"] != "pending":
            return _error("already_processed", 409)
        db.execute("UPDATE cli_devices SET status=?,user_id=? WHERE device_hash=? AND status='pending'",
                   (decision, user["id"], row["device_hash"]))
    return _response({"status": decision})


@router.post("/api/auth/cli/token")
def poll_device(request: Request, payload: dict = Body(...)):
    device = payload.get("device_code")
    if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", device):
        raise HTTPException(400, "device_code 格式无效")
    timestamp = now()
    with connect(global_db=True) as db:
        db.execute("BEGIN IMMEDIATE")
        _cleanup(db, timestamp)
        if not _rate_allowed(db, request, "poll", timestamp, 2400):
            return _error("slow_down", 429, POLL_SECONDS)
        row = db.execute("SELECT * FROM cli_devices WHERE device_hash=?", (_digest(device),)).fetchone()
        if not row:
            return _error("invalid_grant", 400)
        if row["expires_at"] <= timestamp:
            return _error("expired_token", 410)
        if row["status"] == "denied":
            return _error("access_denied", 403)
        if row["redeemed_at"] is not None:
            return _error("invalid_grant", 409)
        if row["last_poll_at"] is not None and timestamp - row["last_poll_at"] < POLL_SECONDS:
            return _error("slow_down", 429, POLL_SECONDS)
        db.execute("UPDATE cli_devices SET last_poll_at=? WHERE device_hash=?", (timestamp, row["device_hash"]))
        if row["status"] == "pending":
            return _error("authorization_pending", 202)
        from .auth import _public_user
        user = db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
        if not user:
            return _error("invalid_grant", 400)
        token = "czz_cli_" + secrets.token_urlsafe(32)
        expires = timestamp + TOKEN_SECONDS
        db.execute("INSERT INTO cli_tokens(id,user_id,token_hash,name,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                   (new_id("cli"), user["id"], _digest(token), row["name"], timestamp, expires))
        db.execute("UPDATE cli_devices SET redeemed_at=? WHERE device_hash=?", (timestamp, row["device_hash"]))
    return _response({"access_token": token, "token_type": "Bearer", "expires_at": expires, "user": _public_user(user)})


@router.get("/api/auth/cli/status")
def cli_status(request: Request):
    from .auth import _public_user
    row = _token_row(request)
    if not row:
        raise HTTPException(401, "请先登录 CLI", headers={"WWW-Authenticate": "Bearer"})
    return _response({"user": _public_user(row), "expires_at": row["cli_expires_at"]})


@router.post("/api/auth/cli/logout")
def cli_logout(request: Request):
    row = _token_row(request)
    if not row:
        raise HTTPException(401, "请先登录 CLI", headers={"WWW-Authenticate": "Bearer"})
    with connect(global_db=True) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE cli_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                   (now(), row["cli_token_id"], row["id"]))
    return _response({"revoked": True})
