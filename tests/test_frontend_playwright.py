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
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
            expect(page.locator(".suitenav a.active")).to_have_text("Processes")
            expect(page.locator("body")).not_to_contain_text("AutonomyLens")

            # Roster: three separated process cards compile to a verdict, each badged "Example".
            page.wait_for_selector('.proc-card[data-demo="expense-reimbursement"]')
            assert page.locator('.proc-card[data-action="open-demo"]').count() == 3
            assert page.locator('.proc-card[data-action="open-demo"] .tag-example').count() == 3
            expect(page.locator('.proc-card[data-demo="expense-reimbursement"] .pill')).to_contain_text(
                "Delegate with human gates"
            )
            expect(page.locator('.proc-card[data-demo="vendor-onboarding"] .pill')).to_contain_text(
                "Do not delegate ungated"
            )
            expect(page.locator('.proc-card[data-demo="billing-inquiry-triage"] .pill')).to_contain_text(
                "Ready to delegate"
            )

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
            page.wait_for_selector('.proc-card[data-demo="expense-reimbursement"]')

            # Open the deployment dossier. While the backend is pending, the compile
            # surface still shows row-level detail instead of bare stage names.
            page.evaluate(
                """() => {
                  const originalFetch = window.fetch.bind(window);
                  window.__releaseNextAnalyze = null;
                  window.fetch = (input, init) => {
                    const url = typeof input === "string" ? input : input.url;
                    const method = (init && init.method) || "GET";
                    if (url.includes("/api/analyze") && method === "POST") {
                      return new Promise((resolve, reject) => {
                        window.__releaseNextAnalyze = () => originalFetch(input, init).then(resolve, reject);
                      });
                    }
                    return originalFetch(input, init);
                  };
                }"""
            )
            page.click('.proc-card[data-demo="expense-reimbursement"]')
            page.wait_for_selector(".compile")
            expect(page.locator(".cstage__detail").first).to_contain_text("Bounded")
            expect(page.locator(".cstage__detail").nth(2)).to_contain_text("Evidence quotes")
            # Honest framing: while the model call is pending the spinner parks on the
            # neural extraction stage, and the symbolic stages stay unsettled (not faked).
            page.wait_for_selector('.cstage[data-i="1"].run')
            assert page.locator(".cstage.run").count() == 1
            assert page.locator('.cstage[data-i="3"].done, .cstage[data-i="3"].warn').count() == 0
            page.evaluate("window.__releaseNextAnalyze && window.__releaseNextAnalyze()")
            # The deterministic compile now parks on an explicit "Open dossier" CTA after
            # the stages settle (matching the model path), instead of auto-opening.
            page.wait_for_selector('button[data-action="open-compiled-dossier"]')
            page.click('button[data-action="open-compiled-dossier"]')
            page.wait_for_selector(".verdict__word")
            expect(page.locator(".verdict__word")).to_contain_text("Delegate with human gates")
            expect(page.locator(".verdict__chips")).to_contain_text("Grounded")

            # Three consolidated sections, each leading with the human-facing one.
            expect(page.locator('.tab[data-tab="plan"]')).to_contain_text("Operating plan")
            expect(page.locator('.tab[data-tab="proof"]')).to_contain_text("Safety proof")
            expect(page.locator('.tab[data-tab="controls"]')).to_contain_text("Controls")
            expect(page.locator('.tab[data-tab="source"]')).to_contain_text("Source SOP")
            page.click('.tab[data-tab="source"]')
            expect(page.locator("#panel-source")).to_contain_text("The Finance analyst receives")
            page.click('.tab[data-tab="plan"]')
            expect(page.locator("#panel-plan")).to_contain_text("Human decisions")

            # Authority map renders lanes with the signal triad.
            page.wait_for_selector(".lane")
            assert page.locator(".lane").count() == 7
            expect(page.locator(".lane--ai").first).to_be_visible()
            expect(page.locator(".lane--gate").first).to_be_visible()

            # Inspector shows the controller approval step with grounded evidence.
            page.click('.lane:has-text("Controller approves requests above")')
            expect(page.locator("#inspector")).to_contain_text("Controller approves requests above")
            expect(page.locator("#inspector .evidence").first).to_be_visible()

            # Dry-run → Safety proof tab fills with ledger, evals, and the audit chain.
            page.click("#simBtn")
            page.wait_for_selector("#proofLedger .ledger__row")
            page.wait_for_function(
                "() => { const t = document.getElementById('proofLedger').innerText;"
                " return t.includes('gate_requested'); }",
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


def test_ai_compile_trace_waits_for_explicit_open(live_server) -> None:
    if playwright_api is None:
        pytest.skip("Playwright package unavailable")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - local browser binaries are optional
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            expect = playwright_api.expect
            page.goto(live_server, wait_until="networkidle")

            trace = [
                {
                    "name": "Perceive source document",
                    "layer": "neural",
                    "status": "complete",
                    "detail": "Normalized and bounded 701 characters of source.",
                },
                {
                    "name": "Extract process graph",
                    "layer": "neural",
                    "status": "complete",
                    "detail": "Extracted 7 source-backed steps and 6 decision gates.",
                },
                {
                    "name": "Ground every claim to source",
                    "layer": "symbolic",
                    "status": "complete",
                    "detail": "Grounded 7/7 steps to source evidence spans.",
                },
                {
                    "name": "Reconcile authority boundaries",
                    "layer": "symbolic",
                    "status": "warning",
                    "detail": "Reconciled authority - 5 human gates, 7 steps blocked, 10 unresolved gaps.",
                },
                {
                    "name": "Compile control contracts",
                    "layer": "symbolic",
                    "status": "complete",
                    "detail": "Generated 7 deterministic contracts (7 audit-required).",
                },
                {
                    "name": "Evaluate & score readiness",
                    "layer": "symbolic",
                    "status": "warning",
                    "detail": "Readiness 34/100 - confidence 53% -> Do not delegate ungated.",
                },
                {
                    "name": "Seal signed audit trace",
                    "layer": "store",
                    "status": "complete",
                    "detail": "Sealed blueprint, contracts, and trace into a reproducible record.",
                },
            ]

            page.evaluate(
                """async (trace) => {
                  const { renderCompile, runCompile } = await import("/static/js/compile.js");
                  renderCompile("Compiling deployment dossier", "model perception -> deterministic control plane", {
                    aiMode: true,
                    charCount: 701,
                    persist: true,
                  });
                  const ctrl = runCompile();
                  await ctrl.finish(trace);
                  window.__compileResolved = false;
                  ctrl.waitForOpenDossier().then(() => {
                    window.__compileResolved = true;
                  });
                }""",
                trace,
            )

            expect(page.locator(".compile")).to_be_visible()
            expect(page.locator(".cstage__detail").nth(5)).to_contain_text("Readiness 34/100")
            expect(page.locator('button[data-action="open-compiled-dossier"]')).to_be_visible()
            assert page.evaluate("window.__compileResolved") is False

            page.click('button[data-action="open-compiled-dossier"]')
            page.wait_for_function("window.__compileResolved === true")
        finally:
            browser.close()


def test_pending_process_card_shows_while_compile_runs(live_server) -> None:
    if playwright_api is None:
        pytest.skip("Playwright package unavailable")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - local browser binaries are optional
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            expect = playwright_api.expect
            page.goto(live_server, wait_until="networkidle")
            page.wait_for_selector('.proc-card[data-action="open-demo"]')

            page.evaluate(
                """() => {
                  const originalFetch = window.fetch.bind(window);
                  window.__releaseNextAnalyze = null;
                  window.fetch = (input, init = {}) => {
                    const url = typeof input === "string" ? input : input.url;
                    const method = init.method || "GET";
                    if (url.includes("/api/analyze") && method === "POST") {
                      return new Promise((resolve, reject) => {
                        window.__releaseNextAnalyze = () => {
                          const body = JSON.parse(init.body);
                          const localInit = {
                            ...init,
                            body: JSON.stringify({ ...body, prefer_ai: false, runtime_mode: "local" }),
                          };
                          originalFetch(input, localInit).then(resolve, reject);
                        };
                      });
                    }
                    return originalFetch(input, init);
                  };
                }"""
            )

            title = "Controller AP Review"
            sop = (
                "The finance analyst reviews the pending approval queue and records evidence for each exception. "
                "If payment approval is missing, the analyst routes the case to the controller before release."
            )
            page.click('[data-action="onboard"]')
            page.fill("#onbTitle", title)
            page.fill("#onbText", sop)
            page.click('[data-action="submit-onboard"]')
            page.wait_for_selector(".compile")

            page.click('.suitenav a[data-nav="processes"]')
            expect(page.locator(".proc-card--pending")).to_contain_text(title)
            expect(page.locator(".proc-card--pending")).to_contain_text("Compiling")
            expect(page.locator(".proc-card--pending")).to_contain_text("Open compile")
            expect(page.locator(".proc-card--pending")).not_to_contain_text("Running")
            expect(page.locator(".proc-card--pending")).not_to_contain_text("pending")

            page.click(".proc-card--pending")
            page.wait_for_selector(".compile")
            expect(page.locator(".compile")).to_contain_text(title)
            page.click('.suitenav a[data-nav="processes"]')
            expect(page.locator(".proc-card--pending")).to_contain_text(title)

            page.evaluate("window.__releaseNextAnalyze && window.__releaseNextAnalyze()")
            page.wait_for_selector(f'.proc-card:has-text("{title}")')
            expect(page.locator(".proc-card--pending")).to_have_count(0)
            expect(page.locator(f'.proc-card:has-text("{title}")')).to_contain_text("Open dossier")
        finally:
            browser.close()


def test_onboard_domain_dropdown_allows_custom_domain(live_server) -> None:
    if playwright_api is None:
        pytest.skip("Playwright package unavailable")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - local browser binaries are optional
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            expect = playwright_api.expect
            page.goto(live_server, wait_until="networkidle")
            page.evaluate("localStorage.removeItem('handoff.customDomains')")

            page.click('[data-action="onboard"]')
            expect(page.locator("#onbDomain")).to_have_value("accounts_payable")
            expect(page.locator(".select__trigger")).to_contain_text("Accounts Payable")

            page.click(".select__trigger")
            expect(page.locator(".select__menu")).to_be_visible()
            expect(page.locator(".select__opt")).to_have_count(4)
            expect(page.locator(".select__opt.is-selected")).to_contain_text("Accounts Payable")
            expect(page.locator(".select__opt.is-selected .select__check")).to_be_visible()

            page.click(".select__add")
            page.fill(".select__add-input", "Treasury Ops")
            page.press(".select__add-input", "Enter")
            expect(page.locator("#onbDomain")).to_have_value("treasury_ops")
            expect(page.locator(".select__trigger")).to_contain_text("Treasury Ops")
            assert "treasury_ops" in page.evaluate("JSON.parse(localStorage.getItem('handoff.customDomains'))")

            page.click(".select__trigger")
            page.keyboard.press("Escape")
            expect(page.locator("#sheetOverlay")).to_be_visible()
            expect(page.locator(".select__menu")).to_be_hidden()

            page.click('[data-action="close-sheet"]')
            page.click('[data-action="onboard"]')
            option_values = page.locator("#onbDomain option").evaluate_all("(opts) => opts.map((o) => o.value)")
            assert "treasury_ops" in option_values
            page.click(".select__trigger")
            page.click('.select__opt[data-value="treasury_ops"]')
            expect(page.locator("#onbDomain")).to_have_value("treasury_ops")
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


def test_model_picker_dropdowns(live_server) -> None:
    if playwright_api is None:
        pytest.skip("Playwright package unavailable")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - local browser binaries are optional
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            expect = playwright_api.expect
            page.goto(live_server, wait_until="networkidle")

            # Open the BYO model drawer from the runtime chip → provider + model dropdowns render.
            page.click("#runtimeChip")
            page.wait_for_selector("#mdlProvider")
            page.wait_for_selector("#mdlModelSel option", state="attached")

            # Selecting Anthropic populates claude-* models.
            page.select_option("#mdlProvider", "anthropic")
            anthropic_models = page.locator("#mdlModelSel option").all_text_contents()
            assert any("claude" in m for m in anthropic_models)

            # Selecting OpenAI changes the model list (options update on provider change).
            page.select_option("#mdlProvider", "openai")
            openai_models = page.locator("#mdlModelSel option").all_text_contents()
            assert any("gpt-4o" in m for m in openai_models)
            assert openai_models != anthropic_models

            # OpenAI-compatible reveals the Base URL field.
            page.select_option("#mdlProvider", "openai_compatible")
            assert page.locator("#mdlBaseField").is_visible()

            # Ollama hides the API key field (keyless).
            page.select_option("#mdlProvider", "ollama")
            assert page.locator("#mdlKeyField").is_hidden()
        finally:
            browser.close()


def test_static_css_has_no_unbounded_viewport_type() -> None:
    css_dir = Path("app/static/css")
    combined = "\n".join(path.read_text() for path in css_dir.glob("*.css"))
    # Fluid type is allowed only when bounded by clamp(); never a bare vw font-size.
    assert not re.search(r"font-size\s*:\s*[\d.]+vw", combined)
