"""Desktop-only confirmation and dismissal UI on isolated fixture APIs."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect


def test_desktop_confirmation_dock_and_failure_dismissal():
    web = Path(__file__).resolve().parents[1] / 'web'
    question = {
        'id': 'question', 'kind': 'question', 'status': 'pending', 'turn_id': 'turn_plan',
        'question': '是否批准 coding-acceptance 的实现计划？',
        'payload': {'options': [
            {'id': 'approve', 'label': '批准计划，开始执行', 'description': '创建检查点、编写文件并运行 unittest；每次写入和命令仍单独审批。'},
            {'id': 'revise', 'label': '需要修改计划', 'description': '告诉我需要调整的步骤或质量门。'},
            {'id': 'cancel', 'label': '取消', 'description': '不执行此任务。'},
        ]},
    }
    failure = {'id': 'failed_task', 'content': '此前的测试任务', 'status': 'consumed', 'run_status': 'failed', 'error': '模型服务暂时不可用'}
    writes = []
    polls = asyncio.Event()

    async def run():
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
            async def route_handler(route):
                path = urlparse(route.request.url).path
                if path == '/workbench.html':
                    await route.fulfill(path=str(web / 'workbench.html'), content_type='text/html'); return
                if path.startswith('/assets/'):
                    candidate = web / path[len('/assets/'):]
                    if candidate.is_file() and candidate.resolve().is_relative_to(web.resolve()):
                        await route.fulfill(path=str(candidate)); return
                if route.request.method != 'GET': writes.append((path, route.request.post_data))
                if path == '/api/resources/agents': data = {'data': [{'id': 'agent', 'name': 'coding agent', 'role_template': 'coding'}]}
                elif path == '/api/threads': data = {'data': [{'id': 'thread', 'name': '桌面交互验收'}]}
                elif path == '/api/threads/thread':
                    data = {'id': 'thread', 'name': '桌面交互验收', 'agent_id': 'agent', 'status': 'waiting_for_input' if question['status'] == 'pending' else 'idle',
                            'messages': [{'id': 'user', 'turn_id': 'turn_plan', 'role': 'user', 'content': '请制定计划，并等待我审批。'},
                                         {'id': 'reply', 'turn_id': 'turn_plan', 'role': 'assistant', 'content': '计划已制定：\n\n1. 创建独立项目 coding-acceptance\n2. 保存 task_checkpoint\n3. 编写 sort.py 和 tests/test_sort.py\n4. 通过 quality_run 运行标准库 unittest\n\n每次写入与命令执行仍等待你的审批。'}]}
                elif path == '/api/threads/thread/queue': data = {'data': [failure]}
                elif path == '/api/threads/thread/interactions':
                    data = {'data': [question]}; polls.set()
                elif path == '/api/threads/thread/queue/failed_task/dismiss':
                    assert route.request.method == 'POST'
                    failure['dismissed_at'] = 123
                    data = {'message': failure, 'dismissed': True}
                elif path == '/api/threads/thread/interactions/question/answer':
                    assert route.request.method == 'POST'
                    answer = json.loads(route.request.post_data)
                    if question['kind'] == 'question':
                        assert answer['answer'] == '请增加逆序输入的测试'
                    else:
                        assert answer['decision'] == 'denied'
                    question.update(status='answered', response=answer)
                    data = {'interaction': question, 'accepted': True}
                elif path == '/api/auth/me': data = {'authenticated': True, 'user': {'id': 'test', 'name': 'Test'}}
                elif path == '/healthz': data = {'name': 'Codezzn'}
                else: data = {'data': []}
                await route.fulfill(content_type='application/json', body=json.dumps(data))
            try:
                await page.route('**/*', route_handler)
                await page.goto('http://confirmation.test/workbench.html#chat')
                dock = page.locator('#chatInteractionDock')
                await expect(dock).to_be_visible()
                assert await page.locator('#messages #interaction_question').count() == 0
                assert await dock.locator('#interaction_question').count() == 1
                bounds = await dock.bounding_box()
                composer = await page.locator('.prompt-dock').bounding_box()
                assert bounds['y'] + bounds['height'] <= composer['y'] + 2
                assert abs(bounds['width'] - composer['width']) < 2
                assert await dock.locator('.interaction-confirmation').evaluate('(el) => getComputedStyle(el).borderTopColor') == 'rgb(221, 214, 254)'
                assert await dock.locator('.interaction-choice').first.evaluate('(el) => getComputedStyle(el).display') == 'flex'
                assert await dock.locator('.interaction-choice').first.evaluate('(el) => getComputedStyle(el).padding') == '8px'
                assert await dock.locator('.interaction-choice strong').first.evaluate('(el) => getComputedStyle(el).fontSize') == '13px'
                assert writes == []
                answer = dock.get_by_role('textbox', name='用自己的话回答')
                await answer.fill('请增加逆序输入的测试')
                polls.clear()
                await asyncio.wait_for(polls.wait(), timeout=4)
                await expect(answer).to_have_value('请增加逆序输入的测试')
                await dock.get_by_role('button', name='收起确认', exact=True).click()
                await expect(page.locator('#interactionBody_question')).to_be_hidden()
                assert writes == []
                await dock.get_by_role('button', name='展开确认', exact=True).click()
                await expect(answer).to_have_value('请增加逆序输入的测试')
                screenshot = os.getenv('CODEZZN_DOCK_QA_SCREENSHOT')
                if screenshot:
                    Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=screenshot, full_page=True)
                await page.locator('#chatQueue').get_by_role('button', name='删除', exact=True).click()
                await expect(page.locator('#chatQueue')).to_be_hidden()
                assert len(writes) == 1 and writes[0][0].endswith('/dismiss')
                await page.reload()
                await expect(page.locator('#chatInteractionDock')).to_be_visible()
                await expect(page.locator('#chatQueue')).to_be_hidden()
                assert await page.locator('#interaction_question').count() == 1
                await page.get_by_role('textbox', name='用自己的话回答').fill('请增加逆序输入的测试')
                await page.get_by_role('textbox', name='用自己的话回答').press('Enter')
                await expect(page.locator('#chatInteractionDock')).to_be_hidden()
                await expect(page.locator('#messages #interaction_question')).to_be_visible()
                assert '请增加逆序输入的测试' in await page.locator('#messages #interaction_question').inner_text()
                assert len(writes) == 2
                assert not any('/queue' == path[-6:] or path.endswith('/turns/active') for path, _ in writes)
                question.update(kind='tool_approval', status='pending', question='允许智能体执行 quality_run？',
                    payload={'tool_name': 'quality_run', 'arguments': {'checks': [{'name': 'test', 'command': 'python -m unittest discover -s tests -v'}]}}, response={})
                await page.reload()
                dock = page.locator('#chatInteractionDock')
                await expect(dock).to_be_visible()
                await expect(dock.get_by_role('button', name='允许并继续', exact=False)).to_be_visible()
                await dock.locator('summary').click()
                assert 'python -m unittest discover' in await dock.locator('pre').inner_text()
                await dock.get_by_role('button', name='拒绝并关闭确认', exact=True).click()
                await expect(dock).to_be_hidden()
                assert json.loads(writes[-1][1])['decision'] == 'denied'
                assert len(writes) == 3
            finally:
                await browser.close()
    asyncio.run(run())
