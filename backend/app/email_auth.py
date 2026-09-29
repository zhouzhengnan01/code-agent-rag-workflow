"""One-time email login codes, independent of the recipient's mail provider."""

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException

from .auth import _public_user
from .db import connect, new_id, now


LOG = logging.getLogger(__name__)
CODE_LIFETIME = 600
RESEND_DELAY = 60
MAX_VERIFY_ATTEMPTS = 5


def smtp_configured() -> bool:
    return bool(all(os.getenv(key) for key in (
        "CODEZZN_SMTP_HOST", "CODEZZN_SMTP_USER", "CODEZZN_SMTP_PASSWORD", "CODEZZN_SMTP_FROM",
    )))


def _email_address(value: str) -> tuple[str, str]:
    try:
        result = validate_email(str(value or "").strip(), check_deliverability=False, allow_smtputf8=True)
    except EmailNotValidError as exc:
        raise HTTPException(400, "请输入有效的邮箱地址") from exc
    normalized = result.normalized.lower()
    if len(normalized) > 254:
        raise HTTPException(400, "邮箱地址过长")
    return normalized, result.ascii_email or result.normalized


def _smtp_settings() -> tuple[str, int, str, str, str, str]:
    if not smtp_configured():
        raise HTTPException(503, "邮箱验证码尚未配置，请设置 SMTP 发信参数")
    security = os.getenv("CODEZZN_SMTP_SECURITY", "ssl").lower()
    if security not in {"ssl", "starttls"}:
        raise HTTPException(503, "SMTP 安全模式必须是 ssl 或 starttls")
    try:
        port = int(os.getenv("CODEZZN_SMTP_PORT") or ("465" if security == "ssl" else "587"))
    except ValueError as exc:
        raise HTTPException(503, "SMTP 端口配置无效") from exc
    if not 1 <= port <= 65535:
        raise HTTPException(503, "SMTP 端口配置无效")
    return (
        os.getenv("CODEZZN_SMTP_HOST"), port, os.getenv("CODEZZN_SMTP_USER"),
        os.getenv("CODEZZN_SMTP_PASSWORD"), os.getenv("CODEZZN_SMTP_FROM"), security,
    )


def _rate_limit(db, bucket: str, limit: int, timestamp: int):
    window_start = timestamp - timestamp % 3600
    row = db.execute("SELECT window_start,attempts FROM auth_rate_limits WHERE bucket=?", (bucket,)).fetchone()
    if row and row["window_start"] == window_start and row["attempts"] >= limit:
        raise HTTPException(429, "发送次数过多，请稍后再试")
    db.execute(
        "INSERT INTO auth_rate_limits(bucket,window_start,attempts) VALUES(?,?,1) "
        "ON CONFLICT(bucket) DO UPDATE SET window_start=excluded.window_start,"
        "attempts=CASE WHEN auth_rate_limits.window_start=excluded.window_start "
        "THEN auth_rate_limits.attempts+1 ELSE 1 END",
        (bucket, window_start),
    )


def _code_hash(code: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt, 150_000).hex()


def _send_code(recipient: str, code: str, settings):
    host, port, username, password, from_address, security = settings
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = recipient
    message["Subject"] = "Codezzn 登录验证码"
    message.set_content(f"你的 Codezzn 登录验证码是：{code}\n\n10 分钟内有效，仅可使用一次。若非本人操作，请忽略此邮件。")
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=10)
    with client:
        if security == "starttls":
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        client.login(username, password)
        client.send_message(message)


def send_email_code(address: str) -> dict:
    settings = _smtp_settings()
    email, recipient = _email_address(address)
    timestamp = now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_bytes(16)
    digest = _code_hash(code, salt)
    with connect(global_db=True) as db:
        db.execute("DELETE FROM email_login_challenges WHERE expires_at<=?", (timestamp,))
        db.execute("DELETE FROM auth_rate_limits WHERE window_start<?", (timestamp - 86400,))
        existing = db.execute("SELECT last_sent_at FROM email_login_challenges WHERE email=?", (email,)).fetchone()
        if existing and existing["last_sent_at"] > timestamp - RESEND_DELAY:
            raise HTTPException(429, "请等待 60 秒后再发送验证码")
        _rate_limit(db, "email-send:" + hashlib.sha256(email.encode()).hexdigest(), 5, timestamp)
        _rate_limit(db, "email-send:global", 100, timestamp)
        db.execute(
            "INSERT INTO email_login_challenges(email,salt,code_hash,created_at,expires_at,last_sent_at,attempts) "
            "VALUES(?,?,?,?,?,?,0) ON CONFLICT(email) DO UPDATE SET "
            "salt=excluded.salt,code_hash=excluded.code_hash,created_at=excluded.created_at,"
            "expires_at=excluded.expires_at,last_sent_at=excluded.last_sent_at,attempts=0",
            (email, salt.hex(), digest, timestamp, timestamp + CODE_LIFETIME, timestamp),
        )
    try:
        _send_code(recipient, code, settings)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        LOG.warning("Email login code delivery failed (%s)", type(exc).__name__)
        with connect(global_db=True) as db:
            db.execute("DELETE FROM email_login_challenges WHERE email=? AND code_hash=?", (email, digest))
        raise HTTPException(502, "邮件发送失败，请检查发信服务配置或稍后再试") from exc
    return {"ok": True, "expires_in": CODE_LIFETIME, "resend_after": RESEND_DELAY}


def verify_email_code(address: str, submitted: str) -> dict:
    email, _ = _email_address(address)
    code = str(submitted or "").strip()
    if len(code) != 6 or not code.isascii() or not code.isdecimal():
        raise HTTPException(400, "验证码不正确或已失效")
    timestamp = now()
    user = None
    error = None
    with connect(global_db=True) as db:
        row = db.execute("SELECT * FROM email_login_challenges WHERE email=?", (email,)).fetchone()
        if not row:
            error = HTTPException(400, "验证码不正确或已失效")
        elif row["expires_at"] <= timestamp:
            db.execute("DELETE FROM email_login_challenges WHERE email=?", (email,))
            error = HTTPException(400, "验证码不正确或已失效")
        elif not hmac.compare_digest(_code_hash(code, bytes.fromhex(row["salt"])), row["code_hash"]):
            if row["attempts"] + 1 >= MAX_VERIFY_ATTEMPTS:
                db.execute("DELETE FROM email_login_challenges WHERE email=?", (email,))
            else:
                db.execute("UPDATE email_login_challenges SET attempts=attempts+1 WHERE email=?", (email,))
            error = HTTPException(400, "验证码不正确或已失效")
        else:
            db.execute("DELETE FROM email_login_challenges WHERE email=?", (email,))
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and not user["password_hash"] and (user["github_id"] or user["google_id"]):
                error = HTTPException(409, "此邮箱已绑定其他登录方式，请使用原账号登录")
            elif not user:
                user_id = new_id("usr")
                name = email.split("@", 1)[0][:80]
                db.execute(
                    "INSERT INTO users(id,email,name,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (user_id, email, name, None, timestamp, timestamp),
                )
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if error:
        raise error
    return _public_user(user)
