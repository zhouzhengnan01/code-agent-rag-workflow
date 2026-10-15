import base64
import json
import io
import os
import re
import zipfile
from urllib.parse import quote, urlsplit

import httpx

from .db import current_tenant


class GitHubError(RuntimeError): pass


def parse_repo(remote):
    value = str(remote).strip()
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", value)
    if not match or match.group(1) in {".", ".."} or match.group(2) in {".", ".."}: raise GitHubError("当前 Git remote 不是可识别的 GitHub 仓库")
    return match.group(1), match.group(2)


def configured_token():
    """Administrator-managed tenant credentials, never OAuth session tokens."""
    user_id = current_tenant()
    if user_id:
        try:
            mapping = json.loads(os.getenv("CODEZZN_GITHUB_USER_TOKENS", "{}"))
        except (TypeError, ValueError) as exc:
            raise GitHubError("CODEZZN_GITHUB_USER_TOKENS 配置格式无效") from exc
        if not isinstance(mapping, dict):
            raise GitHubError("CODEZZN_GITHUB_USER_TOKENS 必须是用户 ID 到 token 的映射")
        token = mapping.get(user_id)
        if token:
            if not isinstance(token, str):
                raise GitHubError("当前用户 GitHub 凭据配置无效")
            return token
        if os.getenv("CODEZZN_GITHUB_ALLOW_SHARED_TOKEN", "false").lower() != "true":
            return ""
    return os.getenv("CODEZZN_GITHUB_TOKEN", "")


async def request(method, remote, path, payload=None):
    token = configured_token()
    if not token: raise GitHubError("未给当前用户配置 GitHub 凭据；请管理员配置 CODEZZN_GITHUB_USER_TOKENS")
    owner, repo = parse_repo(remote)
    url = f"https://api.github.com/repos/{owner}/{repo}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        response = await client.request(method, url, headers=headers, json=payload)
    if response.status_code >= 400: raise GitHubError(f"GitHub API {response.status_code}: {response.text[:1000]}")
    return response.json() if response.content else {}


async def create_pr(remote, title, head, base, body="", draft=False):
    return await request("POST", remote, "pulls", {"title":title,"head":head,"base":base,"body":body,"draft":bool(draft)})


async def ci_status(remote, ref):
    encoded = quote(str(ref), safe="")
    checks = await request("GET", remote, f"commits/{encoded}/check-runs")
    # GitHub accepts either a SHA or a branch in head_sha; URL encoding prevents query injection.
    runs = await request("GET", remote, f"actions/runs?head_sha={encoded}&per_page=30")
    return {"check_runs": checks.get("check_runs", []), "workflow_runs": runs.get("workflow_runs", [])}


async def review_comment(remote, pull_number, body, commit_id, path, line, side="RIGHT"):
    return await request("POST", remote, f"pulls/{int(pull_number)}/comments", {"body":body,"commit_id":commit_id,"path":path,"line":int(line),"side":side})


def auth_header_command():
    token = configured_token()
    if not token: return []
    value = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    # Scope credentials to GitHub, rather than attaching the token to every
    # HTTP remote a model might clone/fetch/push.
    return ["-c", f"http.https://github.com/.extraHeader=Authorization: Basic {value}"]


async def read_pr(remote, pull_number):
    number = int(pull_number)
    if number < 1:
        raise GitHubError("PR 编号必须是正整数")
    info = await request("GET", remote, f"pulls/{number}")
    files = await request("GET", remote, f"pulls/{number}/files?per_page=100")
    comments = await request("GET", remote, f"pulls/{number}/comments?per_page=100")
    discussion = await request("GET", remote, f"issues/{number}/comments?per_page=100")
    return {"pull_request": info, "files": files, "review_comments": comments, "discussion": discussion,
            "pagination_note": "文件和评论各返回前 100 条；大型 PR 需分页继续获取，files.patch 可能被 GitHub 截断"}


async def rerun_ci(remote, run_id, failed_only=True):
    run_id = int(run_id)
    if run_id < 1:
        raise GitHubError("CI run_id 必须是正整数")
    endpoint = "rerun-failed-jobs" if failed_only else "rerun"
    return await request("POST", remote, f"actions/runs/{run_id}/{endpoint}", {})


async def ci_logs(remote, run_id, max_bytes=1024 * 1024):
    """Fetch capped Actions log archive without forwarding tokens to blobs."""
    token = configured_token()
    if not token:
        raise GitHubError("当前用户未配置 GitHub 凭据")
    owner, repo = parse_repo(remote)
    run_id = int(run_id)
    if run_id < 1:
        raise GitHubError("CI run_id 必须是正整数")
    max_bytes = max(1024, min(int(max_bytes), 4 * 1024 * 1024))
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False) as client:
        response = await client.get(url, headers=headers)
        if response.status_code not in (301, 302, 303, 307, 308):
            raise GitHubError(f"GitHub 日志下载未返回授权地址（HTTP {response.status_code}）")
        location = response.headers.get("location", "")
        parsed = urlsplit(location)
        host = parsed.hostname or ""
        allowed = host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com") or host == "github.com"
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or not allowed:
            raise GitHubError("GitHub 日志下载地址不在受信任的 HTTPS 存储域名")
        content = bytearray()
        # No Authorization on the signed download URL; redirects stay disabled.
        async with client.stream("GET", location) as download:
            if download.status_code != 200:
                raise GitHubError(f"GitHub 日志下载失败（HTTP {download.status_code}）")
            async for chunk in download.aiter_bytes():
                content.extend(chunk)
                if len(content) > 20 * 1024 * 1024:
                    raise GitHubError("GitHub 日志压缩包超过 20 MiB 安全上限")
    logs, consumed, truncated = [], 0, False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if len(logs) >= 500 or consumed >= max_bytes:
                    truncated = True
                    break
                with archive.open(entry) as handle:
                    data = handle.read(max_bytes - consumed + 1)
                remaining = max_bytes - consumed
                truncated = truncated or len(data) > remaining
                data = data[:remaining]
                consumed += len(data)
                logs.append({"path": entry.filename[:500], "content": data.decode("utf-8", errors="replace")})
    except (ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        raise GitHubError("GitHub 日志不是可读取的 ZIP 包") from exc
    return {"run_id": run_id, "logs": logs, "bytes": consumed, "truncated": truncated}
