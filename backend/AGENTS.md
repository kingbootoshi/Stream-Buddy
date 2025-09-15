# Repository Guidelines

## Project Structure & Module Organization
- Source code lives in `src/`:
  - `api/` FastAPI routes, WebSocket, overlay event bus.
  - `pipeline/` Pipecat pipeline builder, runner, handlers.
  - `processors/` custom Pipecat processors (mic gate, guards, Twitch source).
  - `services/` factories for STT (AssemblyAI), TTS (ElevenLabs), LLM (OpenRouter), audio.
  - `config/` settings loader and `personality.yaml` system prompt.
  - `core/` shared state and logging setup.
- Entrypoints: `main.py` (runs API + pipeline), `example.py` (Twitch-only demo), `backend/generate_user_token.py` (Twitch user token helper).
- Environment: `.env` at repo root and `backend/.env` are both read; copy from `.env.example`.
- Twitch user token is stored at `backend/.twitch_user_token.json` (keep local).

## Build, Test, and Development Commands
- Setup: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.
- Run app: `python main.py` (starts FastAPI on `127.0.0.1:8710` and the Pipecat pipeline).
- Health check: `curl http://127.0.0.1:8710/healthz`.
- Overlay control (requires header): `curl -X POST http://127.0.0.1:8710/api/listen/toggle -H 'X-Overlay-Key: devlocal'`.
- Twitch token (once per machine): `python backend/generate_user_token.py`.
- Demo bot (optional): `python example.py`.

## Coding Style & Naming Conventions
- Python with type hints; 4-space indentation; PEP 8-ish naming: `snake_case` for functions/variables, `PascalCase` for classes, modules lowercase with underscores.
- Prefer docstrings and f-strings. Use `loguru` for logging (no `print`).
- Configuration flows through `src/config/settings.py::Settings.load()`; avoid reading envs directly in feature code.
- Keep imports relative within `src` packages and avoid circular deps.

## Testing Guidelines
- No formal suite yet. Use `pytest` when adding tests; name files `tests/test_*.py`.
- API tests: `fastapi.testclient` for `/healthz` and overlay routes.
- Unit tests: processors (mic gate, guards, twitch source) with deterministic inputs.
- Mock external services (AssemblyAI, ElevenLabs, OpenRouter, Twitch/HTTPX) to keep tests offline.

## Commit & Pull Request Guidelines
- Commits: concise, imperative summaries (e.g., "Add Twitch chat integration"). Group related changes.
- PRs: include a clear description, linked issues, reproduction steps, and logs/screens where relevant. Update `.env.example`, `requirements.txt`, and docs when adding deps or envs.

## Security & Configuration Tips
- Never commit secrets or tokens. Keep `.env` and `backend/.twitch_user_token.json` local; rotate if leaked.
- Required keys: `ASSEMBLYAI_API_KEY`, `OPENROUTER_API_KEY`, `ELEVENLABS_API_KEY`; Twitch: `TWITCH_*`; overlay header: `X-Overlay-Key` (matches `OVERLAY_KEY`).
- Web endpoints: REST under `/api/*`, WS at `/ws/overlay`.

x

## Docs
- Pipecat Master Guide: `docs/pipecat-master-guide.md`
- Pipeline Diagram (Mermaid): `docs/pipeline.md`