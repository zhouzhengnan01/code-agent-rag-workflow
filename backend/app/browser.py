import asyncio
from pathlib import Path

from .workspace import current_workspace


class BrowserManager:
    def __init__(self): self.playwright = None; self.browser = None; self.contexts = {}

    async def start(self):
        if self.browser: return
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])

    async def close(self):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()
        self.browser = self.playwright = None; self.contexts.clear()

    async def page(self, session="default"):
        await self.start()
        if session not in self.contexts:
            context = await self.browser.new_context(viewport={"width": 1440, "height": 900})
            self.contexts[session] = (context, await context.new_page())
        return self.contexts[session][1]

    async def execute(self, action, session="default", **args):
        page = await self.page(session)
        if action == "navigate":
            response = await page.goto(str(args["url"]), wait_until=args.get("wait_until", "domcontentloaded"), timeout=min(int(args.get("timeout", 30000)), 120000))
            return {"url":page.url,"title":await page.title(),"status":response.status if response else None}
        if action == "inspect":
            selector = args.get("selector") or "body"; items = await page.locator(selector).all()
            result = []
            for item in items[:100]:
                result.append({"text":(await item.inner_text())[:2000],"tag":await item.evaluate("e=>e.tagName"),"attributes":await item.evaluate("e=>Object.fromEntries([...e.attributes].map(a=>[a.name,a.value]))")})
            return {"url":page.url,"selector":selector,"elements":result}
        if action == "click": await page.locator(str(args["selector"])).first.click(); return {"url":page.url}
        if action == "mouse_click": await page.mouse.click(float(args["x"]), float(args["y"])); return {"url":page.url,"x":args["x"],"y":args["y"]}
        if action == "mouse_move": await page.mouse.move(float(args["x"]), float(args["y"])); return {"x":args["x"],"y":args["y"]}
        if action == "scroll": await page.mouse.wheel(float(args.get("delta_x", 0)), float(args.get("delta_y", 700))); return {"scrolled":True}
        if action == "hover": await page.locator(str(args["selector"])).first.hover(); return {"selector":args["selector"]}
        if action == "type": await page.locator(str(args["selector"])).first.fill(str(args.get("text", ""))); return {"typed":True}
        if action == "press": await page.keyboard.press(str(args["key"])); return {"pressed":args["key"]}
        if action == "wait": await page.wait_for_timeout(min(float(args.get("seconds", 1)), 30) * 1000); return {"waited":args.get("seconds",1)}
        if action == "screenshot":
            relative = str(args.get("path") or ".codezzn-artifacts/browser.png"); target = (current_workspace() / relative).resolve(); root = current_workspace().resolve()
            if root not in target.parents: raise ValueError("截图路径超出工作区")
            target.parent.mkdir(parents=True, exist_ok=True); await page.screenshot(path=str(target), full_page=bool(args.get("full_page", True)))
            return {"path":target.relative_to(root).as_posix(),"url":page.url}
        if action == "evaluate": return {"value":await page.evaluate(str(args["script"]))}
        raise ValueError("不支持的浏览器动作")


browser_manager = BrowserManager()
