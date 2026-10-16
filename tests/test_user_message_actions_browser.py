import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.async_api import async_playwright, expect


@pytest.mark.parametrize('clipboard_fallback', [False, True])
def test_desktop_user_message_actions(clipboard_fallback):
    web = Path(__file__).resolve().parents[1] / 'web'
    text = '请编写 **冒泡排序**\n保留空列表和负数测试。'
    writes = []
    poll = asyncio.Event()
    message = {'id': 'user', 'role': 'user', 'content': text, 'created_at': 1735693200, 'meta': {'sent_at': 1735689600}}

    async def run():
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
            await page.add_init_script("""window.__copied=[];
                Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{
                    if(FALLBACK)throw new Error('HTTP fallback');window.__copied.push(text);
                }}});
                document.execCommand=command=>{if(command!=='copy')return false;
                    window.__copied.push(document.querySelector('textarea[style*="-9999"]').value);return true;};
            """.replace('FALLBACK', 'true' if clipboard_fallback else 'false'))

            async def handler(route):
                path = urlparse(route.request.url).path
                if path == '/workbench.html':
                    await route.fulfill(path=str(web / 'workbench.html'), content_type='text/html'); return
                if path.startswith('/assets/'):
                    candidate = web / path[len('/assets/'):]
                    if candidate.is_file() and candidate.resolve().is_relative_to(web.resolve()):
                        await route.fulfill(path=str(candidate)); return
                if route.request.method != 'GET': writes.append((path, route.request.post_data))
                if path == '/api/resources/agents': data = {'data': [{'id': 'agent', 'name': 'coding agent'}]}
                elif path == '/api/threads': data = {'data': [{'id': 'thread', 'name': '消息操作验收'}]}
                elif path == '/api/threads/thread':
                    data = {'id': 'thread', 'name': '消息操作验收', 'agent_id': 'agent', 'status': 'idle', 'messages': [message]}; poll.set()
                elif path == '/api/threads/thread/queue' and route.request.method == 'POST':
                    payload = json.loads(route.request.post_data)
                    data = {'message': {'id': 'new_task', 'status': 'pending', 'run_status': 'pending', 'content': payload['content']}}
                elif path == '/api/auth/me': data = {'authenticated': True, 'user': {'id': 'test', 'name': 'Test'}}
                elif path == '/healthz': data = {'name': 'Codezzn'}
                else: data = {'data': []}
                await route.fulfill(content_type='application/json', body=json.dumps(data))
            try:
                await page.route('**/*', handler)
                await page.goto('http://message.test/workbench.html#chat')
                bubble = page.locator('.user-message-bubble')
                await expect(bubble).to_be_visible()
                actions = bubble.locator('.user-message-actions')
                assert await actions.evaluate('(el)=>getComputedStyle(el).opacity') == '0'
                await bubble.hover()
                await expect(actions).to_have_css('opacity', '1')
                assert await actions.locator('time').inner_text() == '08:00'
                assert '2025' in await actions.locator('time').get_attribute('title')
                await actions.get_by_role('button', name='复制消息').click()
                assert await page.evaluate('window.__copied') == [text]
                assert await page.locator('textarea[style*="-9999"]').count() == 0
                assert writes == []
                screenshot = os.getenv('CODEZZN_MESSAGE_QA_SCREENSHOT')
                if screenshot and not clipboard_fallback:
                    Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=screenshot)
                await actions.get_by_role('button', name='编辑消息').click()
                editor = page.get_by_role('textbox', name='编辑消息内容')
                await expect(editor).to_have_value(text)
                await editor.fill('修改后先取消')
                await page.get_by_role('button', name='取消', exact=True).click()
                assert writes == []
                await page.locator('.user-message-bubble').hover()
                await page.get_by_role('button', name='编辑消息', exact=True).click()
                editor = page.get_by_role('textbox', name='编辑消息内容')
                await editor.fill('请加入逆序输入的测试\n不要安装第三方库。')
                poll.clear()
                await asyncio.wait_for(poll.wait(), timeout=4)
                await expect(editor).to_have_value('请加入逆序输入的测试\n不要安装第三方库。')
                await page.locator('#chatInput').fill('另一个未发送的草稿')
                await page.get_by_role('button', name='重新发送', exact=True).click()
                await expect(page.locator('.user-message-editor')).to_have_count(0)
                assert len(writes) == 1
                assert writes[0][0].endswith('/queue')
                assert json.loads(writes[0][1])['content'] == '请加入逆序输入的测试\n不要安装第三方库。'
                await expect(page.locator('#chatInput')).to_have_value('另一个未发送的草稿')
                assert message['content'] == text
            finally:
                await browser.close()
    asyncio.run(run())
