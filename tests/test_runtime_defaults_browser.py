"""Desktop interaction smoke test using synthetic accounts and an isolated browser."""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect


def test_default_chat_optional_skill_picker_and_permission_selection():
    web = Path(__file__).resolve().parents[1] / 'web'
    writes = []
    thread = {'id': 'thread', 'name': '默认对话', 'agent_id': 'agt_codezzn_default', 'status': 'idle', 'messages': [], 'capability_overrides': {}}
    runtime = {'default_agent_id': 'agt_codezzn_default', 'agent_id': 'agt_codezzn_default', 'permission_mode': 'default', 'skill_discovery': 'auto',
               'skills': [{'id': 'skill_audit', 'name': 'audit-code', 'command': 'audit-code', 'description': '审查代码，不写文件', 'user_invocable': True}]}

    async def run():
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})

            async def handler(route):
                path = urlparse(route.request.url).path
                if path == '/workbench.html':
                    await route.fulfill(path=str(web / 'workbench.html'), content_type='text/html'); return
                if path.startswith('/assets/'):
                    file = web / path[len('/assets/'):]
                    if file.is_file() and file.resolve().is_relative_to(web.resolve()):
                        await route.fulfill(path=str(file)); return
                if route.request.method != 'GET': writes.append((path, route.request.post_data))
                if path == '/api/resources/agents': data = {'data': [{'id': 'custom', 'name': 'Old read-only'}, {'id': 'agt_codezzn_default', 'name': 'Codezzn'}]}
                elif path == '/api/chat/runtime': data = runtime
                elif path == '/api/threads' and route.request.method == 'POST': data = thread
                elif path == '/api/threads': data = {'data': []}
                elif path == '/api/threads/thread' and route.request.method == 'PATCH':
                    thread.update(json.loads(route.request.post_data)); data = thread
                    runtime['permission_mode'] = thread.get('capability_overrides', {}).get('permission_mode', 'default')
                elif path == '/api/threads/thread': data = thread
                elif path == '/api/threads/thread/queue' and route.request.method == 'POST':
                    content = json.loads(route.request.post_data)['content']
                    data = {'message': {'id': 'task', 'content': content, 'run_status': 'pending', 'status': 'pending'}}
                elif path == '/api/auth/me': data = {'authenticated': True, 'user': {'id': 'synthetic', 'name': 'Test'}}
                elif path == '/healthz': data = {'name': 'Codezzn'}
                else: data = {'data': []}
                await route.fulfill(content_type='application/json', body=json.dumps(data))

            try:
                await page.route('**/*', handler)
                await page.goto('http://runtime.test/workbench.html#chat')
                await expect(page.locator('#chatInput')).to_be_visible()
                await expect(page.locator('#chatAgent')).to_have_value('agt_codezzn_default')
                assert writes == []
                await page.locator('#chatInput').fill('/skills')
                await page.locator('#chatInput').press('Enter')
                await expect(page.locator('#skillCommands')).to_be_visible()
                await page.locator('#skillCommands button').click()
                await expect(page.locator('#chatInput')).to_have_value('/audit-code ')
                assert writes == []
                await page.locator('#chatInput').fill('/audit-code 审查当前项目')
                await page.locator('#chatInput').press('Enter')
                await expect(page.locator('#chatInput')).to_have_value('')
                queued = [json.loads(body) for path, body in writes if path.endswith('/queue')]
                assert len(queued) == 1 and queued[0]['content'] == '/audit-code 审查当前项目'
                assert queued[0]['agent_id'] == 'agt_codezzn_default'
                # Inspect default-mode controls; selecting an optional skill never changes permissions.
                assert thread['capability_overrides'] == {}
                await expect(page.locator('#chatPermissionMode')).to_have_value('')
                assert await page.locator('.drawer-layer').count() == 0
            finally:
                await browser.close()
    asyncio.run(run())
