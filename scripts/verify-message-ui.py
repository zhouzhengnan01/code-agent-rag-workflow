"""Real browser UI regression tests; mocked API never deletes real user data."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

root = Path('/app/web')
source = (root / 'workbench.js').read_text(encoding='utf-8')
delete = source[source.index('function deleteThread('):source.index('function projectName(')]
close = source[source.index('function closeModal('):source.index('function field(')]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_content('<main class="message-copy" id="message"></main><div id="modalRoot"></div><button id="trigger">删除</button>')
    page.add_style_tag(path=str(root / 'workbench.css'))
    page.add_script_tag(path=str(root / 'vendor/marked.umd.js'))
    page.add_script_tag(path=str(root / 'vendor/purify.min.js'))
    page.add_script_tag(content='''
      const $ = s => document.querySelector(s);
      const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      let notices=[], requests=[], opened=null, clipboardText=null, rejectNext=false, loaded=0;
      const state={thread:'t1',chatThreads:[{id:'t1',name:'测试会话'}]};
      function getManagedThread(id) {return state.chatThreads.find(t=>t.id===id);}
      function closeSessionMenus() {}
      function toast(text,error) {notices.push({text,error});}
      async function loadPage() {loaded++;}
      async function api(url,options) {requests.push({url,method:options.method});await new Promise(r=>setTimeout(r,50));if(rejectNext){rejectNext=false;throw Error('网络失败');}}
      function openChatArtifact(button) {opened={...button.dataset};}
      document.execCommand = command => {if(command==='copy'){clipboardText=document.activeElement.value;return true;}return false;};
    ''')
    page.add_script_tag(path=str(root / 'message-markdown.js'))
    page.add_script_tag(content=close + delete)
    sample = '''# 标题

**粗体**和*斜体*，~~删除线~~。

1. 第一项
2. 第二项

> 引用文本

| 文件 | 状态 |
| --- | --- |
| `sort.py` | 完成 |

```python
def sort(values):
    return sorted(values)  # <tag> & 中文
```

- [x] 已完成

[文档](https://example.com)
'''
    page.evaluate('''text => {document.querySelector('#message').innerHTML=richText(text,[{path:'sort.py',project_id:'p1',id:'f1'}]);}''', sample)
    assert page.locator('#message h1').inner_text() == '标题'
    assert page.locator('#message ol li').count() == 2
    assert page.locator('#message blockquote').count() == 1
    assert page.locator('#message table').count() == 1
    assert page.locator('#message del').count() == 1
    assert page.locator('#message input[type=checkbox]').is_disabled()
    code = page.locator('#message pre code').inner_text()
    assert code == 'def sort(values):\n    return sorted(values)  # <tag> & 中文\n'
    assert page.locator('.markdown-code-toolbar span').inner_text() == 'python'
    page.get_by_role('button', name='复制代码', exact=True).click()
    page.wait_for_function('clipboardText !== null')
    assert page.evaluate('clipboardText') == code
    assert page.get_by_role('button', name='代码已复制').inner_text() == '已复制'
    page.get_by_role('button', name='在 Files 中打开 sort.py').click()
    assert page.evaluate('opened.artifactId') == 'f1'
    attacks = '<script>window.pwned=1</script><img src=x onerror="window.pwned=2"><svg onload="window.pwned=3"></svg>[bad](javascript:alert(1))<p class="drawer-layer" onclick="alert(1)">test</p>'
    page.evaluate('text => {document.querySelector("#message").innerHTML=richText(text);}', attacks)
    assert page.locator('#message script, #message img, #message svg, #message [onclick], #message .drawer-layer').count() == 0
    assert page.locator('#message a[href^="javascript:"]').count() == 0
    assert page.evaluate('window.pwned || 0') == 0
    page.evaluate('text => {document.querySelector("#message").innerHTML=richText(text);}', '```python\nprint("流式未闭合代码块")')
    assert page.locator('#message pre code').count() == 1
    assert page.locator('.markdown-code-copy').count() == 1
    page.locator('#trigger').focus()
    page.evaluate("deleteThread('t1')")
    assert page.locator('dialog').is_visible()
    assert page.locator('dialog').bounding_box()['width'] <= 440
    assert page.get_by_role('button', name='取消', exact=True).evaluate('(e)=>e===document.activeElement')
    page.get_by_role('button', name='取消', exact=True).click()
    assert page.locator('dialog').count() == 0
    assert page.evaluate('requests.length') == 0
    page.evaluate("deleteThread('t1'); rejectNext=true")
    page.get_by_role('button', name='永久删除', exact=True).click()
    page.wait_for_function('notices.some(n=>n.text==="网络失败")')
    assert page.get_by_role('button', name='永久删除', exact=True).is_enabled()
    page.get_by_role('button', name='永久删除', exact=True).click()
    page.wait_for_function('loaded === 1')
    assert page.evaluate('requests.length') == 2
    assert page.evaluate('requests.every(r=>r.method==="DELETE" && r.url==="/api/threads/t1")')
    assert page.locator('dialog').count() == 0
    assert not errors, errors
    browser.close()
print(json.dumps({'markdown':'passed','copy_http_fallback':'passed','file_links':'passed','xss':'passed','streaming_fence':'passed','compact_delete_cancel':'passed','delete_retry':'passed','page_errors':errors}))
