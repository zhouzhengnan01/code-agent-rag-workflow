from fastapi.testclient import TestClient

from backend.app import db, main


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "landing.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    db.init_db()
    return TestClient(main.app)


def test_public_landing_and_assets_do_not_bypass_workbench_auth(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 200
        assert "Browser Use Agents" in home.text
        assert "/login?next=/workbench.html" in home.text
        assert "/assets/help-widget.js?v=1" in home.text

        hero = client.get("/site-assets/agents-hero-750.webp")
        assert hero.status_code == 200
        assert hero.headers["content-type"].startswith("image/webp")

        css = client.get("/assets/sites/browser-use-com-ef244017/web-agents-4de235c6/base.css")
        assert css.status_code == 200
        assert "--bw-accent:#fe750e" in css.text

        javascript = client.get("/assets/sites/browser-use-com-ef244017/web-agents-4de235c6/landing.js")
        assert javascript.status_code == 200
        assert "data-code-tab" in javascript.text

        workbench = client.get("/workbench.html", follow_redirects=False)
        assert workbench.status_code == 303
        assert workbench.headers["location"] == "/login?next=/workbench.html"

        login = client.get("/login")
        assert login.status_code == 200
        assert "/assets/help-widget.js?v=1" in login.text
        assert "/assets/help-widget.css?v=1" in client.get("/register").text

        faq = client.get("/api/help/faq", params={"q": "项目"})
        assert faq.status_code == 200
        assert any("项目" in item["question"] for item in faq.json()["data"])
        colloquial = client.get("/api/help/faq", params={"q": "怎么保存文件"})
        assert colloquial.json()["data"][0]["id"] == "projects-and-files"
        answer = client.post("/api/help/ask", json={"question": "如何让智能体把代码保存成项目文件？"})
        assert answer.status_code == 200
        assert answer.json()["source"] == "faq"
