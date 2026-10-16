"""Desktop Files acceptance: synthetic project, no business files or model calls."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect


def test_files_tree_sibling_preview_tabs_highlight_resize_and_lifetimes():
    web = Path(__file__).resolve().parents[1] / 'web'
    thread_id, project_id = 'thr_' + '1' * 16, 'prj_' + '2' * 16
    python_id, js_id, html_id, slow_id, error_id = ['art_' + x * 16 for x in ('3', '4', '5', '6', '7')]
    source = '# comment: <img src=x onerror="window.__injected=1">\nfrom typing import List\n\ndef bubble_sort(values):\n    """Return sorted values."""\n    return sorted(values)\n\nprint(bubble_sort([3, 1, 2]))\n'
    files = [{'id': identity, 'path': path, 'size_bytes': 120, 'sha256': identity} for identity, path in (
        (python_id, 'algorithms/sort.py'), (js_id, 'utils.js'), (html_id, 'index.html'), (slow_id, 'slow.py'), (error_id, 'missing.py'))]
    thread = {'id': thread_id, 'name': 'Files 验收', 'agent_id': 'agent', 'active_project_id': project_id, 'status': 'idle', 'messages': []}
    empty_thread = {'id': 'thr_' + '8' * 16, 'name': '隔离验收', 'agent_id': 'agent', 'status': 'idle', 'messages': []}
    attempts, requests = {}, []
    slow_started, slow_release = asyncio.Event(), asyncio.Event()

    async def run():
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
            await page.add_init_script('window.__opened=0;window.open=()=>{window.__opened++;};window.__injected=0;')

            async def handler(route):
                path = urlparse(route.request.url).path; requests.append((route.request.method, path))
                if path == '/workbench.html':
                    await route.fulfill(path=str(web / 'workbench.html'), content_type='text/html'); return
                if path.startswith('/assets/'):
                    file = web / path[len('/assets/'):]
                    if file.is_file() and file.resolve().is_relative_to(web.resolve()):
                        await route.fulfill(path=str(file)); return
                if path == '/api/resources/agents': data = {'data': [{'id': 'agent', 'name': 'Codezzn'}]}
                elif path == '/api/threads': data = {'data': [thread, empty_thread]}
                elif path == f'/api/threads/{thread_id}': data = thread
                elif path == f'/api/threads/{empty_thread["id"]}': data = empty_thread
                elif path == '/api/projects': data = {'data': [{'id': project_id, 'name': 'coding-acceptance'}]}
                elif path == f'/api/projects/{project_id}/artifacts': data = {'data': files}
                elif path.endswith('/content'):
                    identity = path.split('/')[-2]; attempts[identity] = attempts.get(identity, 0) + 1
                    if identity == slow_id:
                        slow_started.set(); await slow_release.wait()
                    if identity == error_id and attempts[identity] == 1:
                        await route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': '暂时无法读取'})); return
                    content = source if identity == python_id else '<script>window.__injected=1</script>' if identity == html_id else '// JS comment\nfunction run() { return 42; }'
                    await route.fulfill(content_type='application/json', body=json.dumps({'content': content})); return
                elif path == '/api/chat/runtime': data = {'permission_mode': 'default', 'skills': []}
                elif path == '/api/auth/me': data = {'authenticated': True, 'user': {'id': 'synthetic', 'name': 'Test'}}
                elif path == '/healthz': data = {'name': 'Codezzn'}
                else: data = {'data': []}
                await route.fulfill(content_type='application/json', body=json.dumps(data))
            try:
                await page.route('**/*', handler)
                await page.goto('http://files.test/workbench.html#chat')
                await expect(page.locator('#filesPanelToggle')).to_contain_text('5')
                await page.locator('#filesPanelToggle').click()
                await expect(page.get_by_role('tree', name='项目文件树')).to_be_visible()
                screenshot = os.getenv('CODEZZN_FILES_QA_SCREENSHOT')
                if screenshot:
                    Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(Path(screenshot).with_name('file-workspace-tree.png')))
                await expect(page.locator('.chat-file-open img').first).to_have_attribute('src', '/assets/vendor/prism/python.png')
                folder = page.locator('details[data-folder-key$=":algorithms"]')
                await folder.locator('summary').click()
                await expect(folder).not_to_have_attribute('open', '')
                await folder.locator('summary').click()
                await page.get_by_role('button', name='查看 algorithms/sort.py', exact=True).click()
                await expect(page.get_by_role('tab', name='sort.py', exact=True)).to_have_attribute('aria-selected', 'true')
                preview = page.locator('.file-source-preview')
                await expect(preview).to_have_text(source)
                await expect(preview.locator('.token.keyword').first).to_have_css('color', 'rgb(0, 0, 159)')
                await expect(preview.locator('.token.comment').first).to_have_css('color', 'rgb(106, 115, 125)')
                assert await preview.locator('img,script').count() == 0
                assert await page.evaluate('window.__opened+window.__injected') == 0
                assert await page.locator('.drawer-layer').count() == 0
                if screenshot:
                    await page.screenshot(path=screenshot)
                await page.get_by_role('tab', name='Files (5)', exact=True).click()
                await page.get_by_role('button', name='查看 utils.js', exact=True).click()
                await expect(page.get_by_role('tab', name='utils.js', exact=True)).to_have_attribute('aria-selected', 'true')
                await page.get_by_role('tab', name='sort.py', exact=True).click()
                await expect(page.locator('.file-source-preview')).to_have_text(source)
                await page.get_by_role('button', name='关闭 sort.py', exact=True).click()
                await expect(page.get_by_role('tab', name='sort.py', exact=True)).to_have_count(0)
                await expect(page.get_by_role('tab', name='utils.js', exact=True)).to_have_attribute('aria-selected', 'true')
                splitter = page.get_by_role('separator', name='调整聊天与文件面板宽度')
                before = float(await splitter.get_attribute('aria-valuenow'))
                await splitter.press('ArrowRight')
                assert float(await splitter.get_attribute('aria-valuenow')) == before + 2
                bounds = await splitter.bounding_box(); chat_before = (await page.locator('.conversation').bounding_box())['width']
                await page.mouse.move(bounds['x'] + 6, bounds['y'] + 200); await page.mouse.down()
                await page.mouse.move(bounds['x'] - 100, bounds['y'] + 200, steps=5); await page.mouse.up()
                assert (await page.locator('.conversation').bounding_box())['width'] < chat_before - 70
                assert not await page.locator('body').evaluate("el=>el.classList.contains('is-resizing-files')")
                assert await page.evaluate("localStorage.getItem('codezzn.files.chatRatio')")
                await page.get_by_role('tab', name='Files (5)', exact=True).click()
                await page.get_by_role('button', name='查看 index.html', exact=True).click()
                await expect(page.locator('.file-source-preview')).to_have_text('<script>window.__injected=1</script>')
                assert await page.evaluate('window.__injected') == 0
                await page.get_by_role('tab', name='Files (5)', exact=True).click()
                await page.get_by_role('button', name='查看 missing.py', exact=True).click()
                await expect(page.locator('.file-preview-status')).to_contain_text('暂时无法读取')
                await page.get_by_role('button', name='重试读取').click()
                await expect(page.locator('.file-source-preview')).to_contain_text('function run')
                await page.get_by_role('tab', name='Files (5)', exact=True).click()
                await page.get_by_role('button', name='查看 slow.py', exact=True).click()
                await asyncio.wait_for(slow_started.wait(), timeout=5)
                await page.get_by_role('button', name='关闭 slow.py', exact=True).click()
                slow_release.set()
                await expect(page.get_by_role('tab', name='slow.py', exact=True)).to_have_count(0)
                await page.get_by_role('button', name='打开会话 隔离验收', exact=True).click()
                await expect(page.locator('.conversation-title')).to_contain_text('隔离验收')
                await expect(page.locator('#filesPanelToggle')).to_be_hidden()
                await expect(page.get_by_role('tab', name='utils.js', exact=True)).to_have_count(0)
                assert await page.evaluate('state.fileWorkspace.tabs.length') == 0
                assert not [method for method, _ in requests if method not in {'GET', 'HEAD'}]
                assert await page.evaluate('window.__opened+window.__injected') == 0
            finally:
                slow_release.set(); await browser.close()
    asyncio.run(run())
