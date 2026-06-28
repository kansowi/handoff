import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


try:
    import playwright.sync_api as playwright_api
except Exception:  # noqa: BLE001 - browser smoke is optional in local environments
    playwright_api = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_server():
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Frontend smoke server did not start")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def test_frontend_deployment_dossier_smoke(live_server) -> None:
    if playwright_api is None:
        pytest.skip("Playwright package unavailable")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - local browser binaries are optional
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            expect = playwright_api.expect

            page.goto(live_server, wait_until="networkidle")
            expect(page).to_have_title(re.compile("Handoff"))
            expect(page.locator(".suitenav a.active")).to_have_text("Processes")
            expect(page.locator("body")).not_to_contain_text("AutonomyLens")

            # Roster: three separated process cards compile to a verdict.
            page.wait_for_selector('.proc-card[data-demo="invoice-exceptions"]')
            assert page.locator('.proc-card[data-action="open-demo"]').count() == 3

            # No invisible text: the card title color must differ from its background.
            title_color, card_bg = page.evaluate(
                """() => {
                  const c = document.querySelector('.proc-card[data-action="open-demo"]');
                  const t = c.querySelector('.proc-card__title');
                  return [getComputedStyle(t).color, getComputedStyle(c).backgroundColor];
                }"""
            )
            assert title_color != card_bg

            # Theme toggle flips data-theme and persists the choice.
            start_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            page.click("#themeToggle")
            assert page.evaluate("document.documentElement.getAttribute('data-theme')") != start_theme
            assert page.evaluate("localStorage.getItem('handoff.theme')") in ("light", "dark")

            # Nav reaches the Trust Center and Run Ledger views.
            page.click('.suitenav a[data-nav="trust"]')
            expect(page.locator(".bigstat").first).to_be_visible()
            page.click('.suitenav a[data-nav="ledger"]')
            page.wait_for_selector(".view-head")
            page.click('.suitenav a[data-nav="processes"]')
            page.wait_for_selector('.proc-card[data-demo="invoice-exceptions"]')

            # Open the deployment dossier (deterministic engine, instant).
            page.click('.proc-card[data-demo="invoice-exceptions"]')
            page.wait_for_selector(".verdict__word")
            expect(page.locator(".verdict__word")).to_contain_text("Do not delegate ungated")
            expect(page.locator(".verdict__chips")).to_contain_text("Grounded")

            # Three consolidated sections, each leading with the human-facing one.
            expect(page.locator('.tab[data-tab="plan"]')).to_contain_text("Operating plan")
            expect(page.locator('.tab[data-tab="proof"]')).to_contain_text("Safety proof")
            expect(page.locator('.tab[data-tab="controls"]')).to_contain_text("Controls")
            expect(page.locator("#panel-plan")).to_contain_text("Human decisions")

            # Authority map renders lanes with the signal triad.
            page.wait_for_selector(".lane")
            assert page.locator(".lane").count() == 8
            expect(page.locator(".lane--ai").first).to_be_visible()
            expect(page.locator(".lane--block").first).to_be_visible()

            # Inspector shows the bank-detail step with grounded evidence.
            page.click('.lane:has-text("Confirm changed bank details")')
            expect(page.locator("#inspector")).to_contain_text("Confirm changed bank details")
            expect(page.locator("#inspector .evidence").first).to_be_visible()

            # Dry-run → Safety proof tab fills with ledger, evals, and the audit chain.
            page.click("#simBtn")
            page.wait_for_selector("#proofLedger .ledger__row")
            page.wait_for_function(
                "() => { const t = document.getElementById('proofLedger').innerText;"
                " return t.includes('blocked') && t.includes('gate_requested'); }",
                timeout=10000,
            )
            expect(page.locator("#proofEvals")).to_contain_text("grounded")
            page.wait_for_selector("#proofAudit .chain__hash")
            expect(page.locator("#proofAudit")).to_contain_text("Source document")
            expect(page.locator("#proofAudit .chain__hash").first).to_contain_text("sha256")

            # Controls tab exposes typed contracts with idempotency keys.
            page.click('.tab[data-tab="controls"]')
            expect(page.locator("#panel-controls")).to_contain_text("idempotency")

            _assert_layout_integrity(page, 1440, 1000)
            _assert_layout_integrity(page, 1120, 900)
            _assert_layout_integrity(page, 720, 900)
            _assert_layout_integrity(page, 390, 844)
        finally:
            browser.close()


def _assert_layout_integrity(page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_timeout(180)
    # No page-level horizontal overflow at any breakpoint.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    # The sticky suite bar stays above scrolling content.
    assert page.evaluate(
        "Number(getComputedStyle(document.querySelector('.suitebar')).zIndex || 0) >= 50"
    )


def test_static_css_has_no_unbounded_viewport_type() -> None:
    css_dir = Path("app/static/css")
    combined = "\n".join(path.read_text() for path in css_dir.glob("*.css"))
    # Fluid type is allowed only when bounded by clamp(); never a bare vw font-size.
    assert not re.search(r"font-size\s*:\s*[\d.]+vw", combined)
