"""Native Node CLI against an isolated real HTTP server; no paid model calls."""
import asyncio
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from backend.app import auth, cli_auth, conversation_control, db, main, workspace


@pytest.mark.skipif(os.name != 'nt', reason='Exercises native Windows DPAPI credential persistence')
def test_windows_cli_browser_login_stream_resume_and_logout(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'data' / 'codezzn.db'))
    monkeypatch.setattr(workspace, 'BASE_WORKSPACE', tmp_path / 'workspace')
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'true')
    monkeypatch.delenv('CODEZZN_ADMIN_KEY', raising=False)
    monkeypatch.delenv('CODEZZN_LEGACY_OWNER_GITHUB_ID', raising=False)
    monkeypatch.setattr(os, 'chown', lambda *args: None, raising=False)
    monkeypatch.setattr(os, 'fchown', lambda *args: None, raising=False)
    db.init_db()
    user = auth.register_user('CLI E2E', 'cli-e2e@example.invalid', 'isolated-test-password')
    cookie, _ = auth.create_session(user['id'])
    tenant = db.use_tenant(user['id'])
    try:
        db.ensure_tenant(user['id'])
        provider = db.resource_save('providers', {'name': 'Mock', 'api_key': 'test-only', 'base_url': 'https://example.invalid', 'models': ['mock-text'], 'default_model': 'mock-text'})
        agent = db.resource_save('agents', {'name': 'CLI E2E Agent', 'provider_id': provider['id'], 'model': 'mock-text', 'memory_enabled': False, 'sandbox_mode': 'read-only'})
    finally:
        db.reset_tenant(tenant)
    calls = []

    async def fake_agent(scoped, history, content, **kwargs):
        calls.append(content)
        emit = kwargs.get('on_event')
        if emit:
            await emit({'id': db.new_id('evt'), 'type': 'assistant_delta', 'content': 'CLI '})
            await asyncio.sleep(.15)
            await emit({'id': db.new_id('evt'), 'type': 'assistant_delta', 'content': '测试通过'})
        return {'status': 'completed', 'content': 'CLI 测试通过', 'events': [], 'usage': {}, 'runtime': {}, 'sources': []}

    async def no_destination(*args, **kwargs):
        return {'requires_project': False, 'kind': 'answer'}

    monkeypatch.setattr(main, 'run_agent_isolated', fake_agent)
    monkeypatch.setattr(main, 'classify_intent', no_destination)
    runtime = conversation_control.ConversationRuntime()
    monkeypatch.setattr(conversation_control, 'conversation_runtime', runtime)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
    monkeypatch.setenv('CODEZZN_PUBLIC_URL', origin)
    server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', log_level='error'))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert worker.is_alive() and time.monotonic() < deadline, 'Isolated server failed to start'
        time.sleep(.05)
    repo = Path(__file__).resolve().parents[1]
    command = ['node', str(repo / 'cli' / 'bin' / 'codezzn.js')]
    env = {**os.environ, 'CODEZZN_CONFIG_DIR': str(tmp_path / 'cli-config')}
    env.pop('CODEZZN_SERVER', None)
    login = None
    try:
        login = subprocess.Popen([*command, 'auth', 'login', '--server', origin, '--no-browser'], cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        output = []

        def read_login():
            for line in login.stderr:
                output.append(line)

        reader = threading.Thread(target=read_login, daemon=True)
        reader.start()
        deadline = time.monotonic() + 10
        code = None
        while not code:
            match = re.search(r'Verification code: ([A-Z0-9-]+)', ''.join(output))
            if match:
                code = match.group(1)
                break
            assert login.poll() is None and time.monotonic() < deadline, 'CLI did not present a device code: ' + ''.join(output)
            time.sleep(.05)
        with httpx.Client(base_url=origin, cookies={auth.SESSION_COOKIE: cookie}, timeout=10, trust_env=False) as browser:
            info = browser.get('/api/auth/cli/device-info', params={'user_code': code})
            assert info.status_code == 200
            approve = browser.post('/api/auth/cli/approve', json={'user_code': code, 'decision': 'approved'}, headers={'Origin': origin, 'X-CLI-CSRF': info.json()['csrf_token']})
            assert approve.status_code == 200
        login.wait(timeout=15)
        reader.join(timeout=3)
        assert login.returncode == 0, ''.join(output)
        credentials = json.loads((tmp_path / 'cli-config' / 'credentials.json').read_text())
        assert credentials['scheme'] == 'dpapi-current-user'
        assert 'czz_cli_' not in json.dumps(credentials)
        status = subprocess.run([*command, 'auth', 'status', '--server', origin], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        assert status.returncode == 0, status.stderr
        first = subprocess.run([*command, '-p', '--server', origin, '--agent', agent['id'], '--output-format', 'stream-json', '隔离测试'], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert first.returncode == 0, first.stderr
        events = [json.loads(line) for line in first.stdout.splitlines() if line.strip()]
        assert any(item.get('type') == 'assistant_delta' for item in events), events
        assert any(item.get('type') == 'result' and item.get('status') == 'completed' for item in events), events
        sessions = json.loads((tmp_path / 'cli-config' / 'sessions.json').read_text())
        session_id = sessions[0]['id']
        second = subprocess.run([*command, '-p', '-c', '--server', origin, '--output-format', 'json', '继续隔离测试'], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert second.returncode == 0, second.stderr
        assert json.loads(second.stdout)['status'] == 'completed'
        assert json.loads((tmp_path / 'cli-config' / 'sessions.json').read_text())[0]['id'] == session_id
        assert calls == ['隔离测试', '继续隔离测试']
        logout = subprocess.run([*command, 'auth', 'logout', '--server', origin], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        assert logout.returncode == 0, logout.stderr
        after = subprocess.run([*command, 'auth', 'status', '--server', origin], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        assert after.returncode == 1
    finally:
        if login is not None and login.poll() is None:
            login.kill()
            login.wait(timeout=5)
        server.should_exit = True
        worker.join(timeout=15)
        assert not worker.is_alive(), 'Isolated server cleanup failed'
