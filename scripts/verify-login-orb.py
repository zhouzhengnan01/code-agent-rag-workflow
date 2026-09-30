"""Exercise the actual login GPU animation without submitting authentication."""

import hashlib
import json
import os

from playwright.sync_api import sync_playwright


def main():
    base = os.environ.get("ORB_TEST_URL", "http://host.docker.internal:8091/login")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(base, wait_until="networkidle")
        orb = page.locator("#authParticleField")
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'running'")
        state = page.evaluate("""() => {
            const canvas = document.querySelector('#authParticleField');
            const pane = document.querySelector('.auth-pane--particle');
            const gl = canvas.getContext('webgl2');
            return {radius: +canvas.dataset.orbRadius,
                particles: +canvas.dataset.orbParticles, error: gl.getError(),
                verticalOverflow: pane.scrollHeight > pane.clientHeight,
                horizontalOverflow: pane.scrollWidth > pane.clientWidth};
        }""")
        assert state["radius"] == 330, state
        assert state["particles"] > 0 and state["error"] == 0, state
        assert not state["verticalOverflow"] and not state["horizontalOverflow"], state

        clip = {"x": 0, "y": 0, "width": 640, "height": 720}
        snapshot = lambda: hashlib.sha256(page.screenshot(clip=clip)).hexdigest()
        first = snapshot()
        page.wait_for_timeout(400)
        assert snapshot() != first, "Animation is not advancing"

        toggle = page.locator(".auth-promo__motion")
        toggle.click()
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'paused'")
        page.mouse.move(900, 650)
        page.wait_for_timeout(200)
        frozen = snapshot()
        page.wait_for_timeout(400)
        assert snapshot() == frozen, "Shared motion toggle did not freeze the orb"
        toggle.click()
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'running'")

        # Mouse interaction does not steal clicks from the existing auth form.
        page.mouse.move(310, 220)
        page.mouse.move(360, 250)
        page.locator('[data-provider="email"]').click()
        page.locator("#emailEntry").fill("orb-qa@example.invalid")

        # Simulated GPU loss must recover without reloading the login form.
        page.evaluate("""() => {
            window.orbQaLoss = document.querySelector('#authParticleField')
                .getContext('webgl2').getExtension('WEBGL_lose_context');
            if (!window.orbQaLoss) throw new Error('Context-loss extension unavailable');
            window.orbQaLoss.loseContext();
        }""")
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'context-lost'")
        page.wait_for_timeout(200)
        page.evaluate("window.orbQaLoss.restoreContext()")
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'running'")
        assert page.locator("#emailEntry").input_value() == "orb-qa@example.invalid"

        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'paused'")
        page.wait_for_timeout(200)
        frozen = snapshot()
        page.wait_for_timeout(400)
        assert snapshot() == frozen, "Reduced-motion rendering is not static"
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'running'")

        page.set_viewport_size({"width": 390, "height": 844})
        assert orb.is_hidden(), "Original phone performance guard is missing"
        page.set_viewport_size({"width": 1280, "height": 720})
        page.wait_for_function("document.querySelector('#authParticleField').dataset.orbStatus === 'running'")
        assert not failures, failures
        print(json.dumps({"gpu": state, "motion": "passed", "shared_pause": "passed",
            "context_restore": "passed", "form_retained": "passed",
            "reduced_motion": "passed", "responsive": "passed", "page_errors": failures}))
        browser.close()


if __name__ == "__main__":
    main()
