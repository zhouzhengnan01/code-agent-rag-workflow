"""Opt-in installed-browser test channel; never reuse a user's browser profile."""
import os

import pytest


@pytest.fixture(autouse=True)
def configured_test_browser_channel(monkeypatch):
    channel = os.getenv("CODEZZN_TEST_BROWSER_CHANNEL", "").strip()
    if not channel: return
    if channel not in {"chromium", "chrome", "chrome-beta", "chrome-dev", "chrome-canary", "msedge", "msedge-beta", "msedge-dev", "msedge-canary"}:
        pytest.fail("Unsupported CODEZZN_TEST_BROWSER_CHANNEL")
    from playwright.async_api import BrowserType as AsyncBrowserType
    from playwright.sync_api import BrowserType as SyncBrowserType
    original_async, original_sync = AsyncBrowserType.launch, SyncBrowserType.launch

    async def async_launch(browser_type, *args, **kwargs):
        kwargs.setdefault("channel", channel)
        return await original_async(browser_type, *args, **kwargs)

    def sync_launch(browser_type, *args, **kwargs):
        kwargs.setdefault("channel", channel)
        return original_sync(browser_type, *args, **kwargs)

    monkeypatch.setattr(AsyncBrowserType, "launch", async_launch)
    monkeypatch.setattr(SyncBrowserType, "launch", sync_launch)
