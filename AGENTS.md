# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.12 FastAPI app for generating agent-ready handoff briefs. Core backend code lives in `app/`: `main.py` defines API routes, `analyzer.py` handles deterministic analysis, `llm.py` wraps optional LiteLLM calls, and `models.py`/`contracts.py` define typed data contracts. Static frontend files are in `app/static/` (`index.html`, `app.js`, `styles.css`). Tests live in `tests/`, with analyzer/API coverage in `test_analyzer.py` and browser smoke coverage in `test_frontend_playwright.py`. Local runtime data belongs in `.data/`; credentials belong in `.env`, copied from `.env.example`.

## Build, Test, and Development Commands

- `python3 -m pip install -r requirements.txt`: install runtime dependencies.
- `python3 -m pip install -e ".[test]"`: install the package plus pytest and Playwright test extras.
- `python3 -m uvicorn app.main:app --reload --port 8010`: run the local app at `http://127.0.0.1:8010`.
- `python3 -m pytest`: run all tests configured under `tests/`.
- `python3 -m playwright install chromium`: install the browser binary needed for the optional frontend smoke test.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and clear function names in Python. Follow existing naming: modules, functions, fixtures, and tests use `snake_case`; Pydantic models and classes use `PascalCase`; frontend DOM IDs use descriptive `camelCase` names such as `analyzeButton`. Keep deterministic analyzer behavior separate from optional AI behavior so local execution remains reliable without credentials.

## Testing Guidelines

Use pytest for backend and integration tests. Name new tests `test_<behavior>` and keep fixtures local unless they are reused broadly. Add analyzer tests for parsing, scoring, or contract changes, and API tests for response-shape changes. Frontend behavior that affects user workflows should be covered in `test_frontend_playwright.py`; tests should skip cleanly when Playwright binaries are unavailable.

## Commit & Pull Request Guidelines

This repository currently has no committed history, so there is no established commit convention. Use concise imperative commits with an optional scope, for example `analyzer: detect timeout gaps`. Pull requests should include a short problem/solution summary, test results, linked issues if applicable, and screenshots for visible UI changes.

## Security & Configuration Tips

Do not commit `.env`, API keys, `.data/*.sqlite3*`, `__pycache__/`, or `.DS_Store`. Keep new configuration documented in `.env.example` and ensure the app still falls back to the deterministic local analyzer when LiteLLM credentials are absent.
