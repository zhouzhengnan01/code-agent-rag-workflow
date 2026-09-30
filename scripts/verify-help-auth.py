"""Anonymous/login pages must never mount the help assistant."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    for path, logged_in, expected in [('/login', True, False), ('/register', True, False), ('/', True, False), ('/workbench.html', False, False), ('/workbench.html', True, True)]:
        page = browser.new_page()
        page.route('http://codezzn.test/**', lambda route: route.fulfill(body='<html><body>测试</body></html>', content_type='text/html'))
        page.route('**/api/auth/me', lambda route: route.fulfill(json={'authenticated': logged_in, 'user': {'id':'usr_test'} if logged_in else None}))
        page.route('**/api/help/ask', lambda route: route.fulfill(status=401, json={'detail':'Unauthorized'}))
        page.goto('http://codezzn.test' + path)
        page.add_script_tag(path='/app/web/help-widget.js')
        page.wait_for_timeout(250)
        assert bool(page.locator('.cz-help-widget').count()) == expected, (path, logged_in)
        if expected:
            page.locator('.cz-help-toggle').click()
            page.locator('.cz-help-chat-link').click()
            page.locator('.cz-help-input').fill('会话过期测试')
            page.locator('.cz-help-send').click()
            page.locator('.cz-help-widget').wait_for(state='detached')
        page.close()
    browser.close()
print(json.dumps({'login_register_home_hidden':'passed','anonymous_hidden':'passed','authenticated_visible':'passed','session_expiry_removes_widget':'passed'}))
