import base64
import os
import re
from urllib.parse import quote

import httpx


class GitHubError(RuntimeError): pass


def parse_repo(remote):
    value = str(remote).strip()
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", value)
    if not match: raise GitHubError("当前 Git remote 不是可识别的 GitHub 仓库")
    return match.group(1), match.group(2)


async def request(method, remote, path, payload=None):
    token = os.getenv("CODEZZN_GITHUB_TOKEN", "")
    if not token: raise GitHubError("未配置 CODEZZN_GITHUB_TOKEN")
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
    token = os.getenv("CODEZZN_GITHUB_TOKEN", "")
    if not token: return []
    value = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraHeader=Authorization: Basic {value}"]
