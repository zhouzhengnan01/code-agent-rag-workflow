import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright


def test_real_browser_engineering_panel_never_auto_submits_or_approves():
    web = Path(__file__).resolve().parents[1] / 'web'
    writes = []
    async def run():
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width':1280,'height':900})
            async def route_handler(route):
                path = urlparse(route.request.url).path
                if path == '/workbench.html':
                    await route.fulfill(path=str(web/'workbench.html'), content_type='text/html'); return
                if path.startswith('/assets/'):
                    candidate = web / path[len('/assets/'):]
                    if candidate.is_file() and candidate.resolve().is_relative_to(web.resolve()):
                        await route.fulfill(path=str(candidate)); return
                if route.request.method != 'GET': writes.append((path, route.request.post_data))
                if path == '/api/resources/agents': data={'data':[{'id':'agent','name':'Coding','role_template':'coding'}]}
                elif path == '/api/threads': data={'data':[{'id':'thread','name':'UI test'}]}
                elif path == '/api/threads/thread': data={'id':'thread','name':'UI test','agent_id':'agent','messages':[],'status':'idle'}
                elif path == '/api/threads/thread/coding/state':
                    data={'workspace':{'path':'<script>unsafe</script>'},'engineering':{'plan':{'status':'proposed','revision':3,'steps':[{'content':'Implement test','status':'pending'}]}},'checkpoints':[{'id':'chk_test','label':'Before edit'}],'context':{'estimated_tokens':200}}
                elif path == '/api/threads/thread/coding/inspect':
                    assert json.loads(route.request.post_data)=={'name':'task_diff','args':{'checkpoint_id':'chk_test'}}
                    data={'result':{'changes':[{'path':'sort.py','diff':'-old\n+new\n'}],'expected_hashes':{'sort.py':'abc'}}}
                elif path == '/api/auth/me': data={'authenticated':True,'user':{'id':'user','name':'Test'}}
                elif path == '/healthz': data={'name':'Codezzn'}
                else: data={'data':[]}
                await route.fulfill(content_type='application/json', body=json.dumps(data))
            try:
                await page.route('**/*', route_handler)
                await page.goto('http://coding.test/workbench.html#chat')
                await page.get_by_role('button',name='工程',exact=True).click()
                dialog=page.get_by_role('dialog',name='工程工作台')
                await dialog.get_by_text('Implement test',exact=False).wait_for()
                assert await dialog.locator('script').count()==0
                await dialog.get_by_role('tab',name='快照 / Diff').click()
                await dialog.get_by_role('button',name='查看 Diff',exact=True).click()
                await dialog.locator('.coding-diff .added').wait_for()
                await dialog.get_by_role('button',name='在对话中请求回退').click()
                await dialog.wait_for(state='hidden')
                prompt=await page.locator('#chatInput').input_value()
                assert 'task_rewind' in prompt and 'expected_hashes' in prompt and '必须等待我的工具审批' in prompt
                assert [path for path,_ in writes]==['/api/threads/thread/coding/inspect']
            finally:
                await browser.close()
    asyncio.run(run())
