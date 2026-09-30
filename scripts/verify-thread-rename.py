"""Browser regression test for inline session renaming; no production data touched."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

source = Path('/app/web/workbench.js').read_text(encoding='utf-8')
rename = source[source.index('let activeThreadRename = null;'):source.index('async function archiveThread(')]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    page.set_content('''<div class="session-item" data-thread-id="t1"><button class="session-open"><span class="session-name">原名称</span></button><button class="session-more">菜单</button></div><div class="conversation-title"><strong>原名称</strong></div><button id="outside">其他位置</button>''')
    page.add_script_tag(content='''
      const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
      const state = {thread:'t1', chatThreads:[{id:'t1',name:'原名称'}]};
      function getManagedThread(id) { return state.chatThreads.find(t => t.id === id); }
      function closeSessionMenus() {}
      let calls = [], errors = [], rejectNext = false;
      function toast(text, error) { if (error) errors.push(text); }
      async function api(url, options) { calls.push(JSON.parse(options.body)); await new Promise(r => setTimeout(r, 30)); if(rejectNext) {rejectNext=false;throw new Error('网络失败');} }
    ''' + rename)
    page.evaluate("renameThread('t1')")
    editor = page.get_by_role('textbox', name='会话名称')
    assert editor.input_value() == '原名称'
    assert page.evaluate('document.activeElement.selectionEnd') == 3
    editor.fill('新名称')
    editor.press('Enter')
    page.wait_for_function('calls.length === 1 && !document.querySelector(".session-rename-input")')
    assert page.locator('.session-name').inner_text() == '新名称'
    assert page.locator('.conversation-title strong').inner_text() == '新名称'
    page.evaluate("renameThread('t1')")
    editor.fill('不保存')
    editor.press('Escape')
    assert page.locator('.session-name').inner_text() == '新名称'
    assert page.evaluate('calls.length') == 1
    page.evaluate("renameThread('t1')")
    editor.fill('失焦保存')
    page.locator('#outside').click()
    page.wait_for_function('calls.length === 2 && !document.querySelector(".session-rename-input")')
    page.evaluate("renameThread('t1')")
    editor.fill('')
    editor.press('Enter')
    assert page.evaluate('calls.length') == 2
    assert page.locator('.session-name').inner_text() == '失焦保存'
    page.evaluate("renameThread('t1'); rejectNext = true")
    editor.fill('重试名称')
    editor.press('Enter')
    page.wait_for_function('errors.includes("网络失败")')
    assert editor.input_value() == '重试名称'
    assert page.locator('.conversation-title strong').inner_text() == '失焦保存'
    editor.press('Enter')
    page.wait_for_function('calls.length === 4 && !document.querySelector(".session-rename-input")')
    page.evaluate("renameThread('t1')")
    editor.fill('中文输入')
    editor.dispatch_event('compositionstart')
    editor.press('Enter')
    assert page.evaluate('calls.length') == 4
    editor.dispatch_event('compositionend')
    editor.press('Enter')
    page.wait_for_function('calls.length === 5 && !document.querySelector(".session-rename-input")')
    page.evaluate("renameThread('t1')")
    editor.fill('<img src=x onerror=alert(1)>')
    editor.press('Enter')
    page.wait_for_function('calls.length === 6 && !document.querySelector(".session-rename-input")')
    assert page.locator('.session-name img').count() == 0
    assert page.locator('.session-name').inner_text() == '<img src=x onerror=alert(1)>'
    browser.close()
print(json.dumps({'inline_rename':'passed','enter':'passed','escape':'passed','blur':'passed','empty':'passed','retry':'passed','ime':'passed','safe_text':'passed'}))
