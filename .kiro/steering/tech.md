---
inclusion: always
---
# Tech

- Python 3.12, FastAPI, SQLite (app/store.py), plain HTML/JS pages in web/ (no build step).
- Bee: the official `bee` CLI with `--json` (app/bee.py). The sample day in fixtures/ is used when the CLI isn't installed (BEE_MODE=demo).
- AI: Together AI by default (app/llm.py, `TOGETHER_MODEL`), Claude API or Amazon Bedrock as options. Every call uses a JSON schema; prompts and schemas are in app/digest.py.
- MCP server (Alexa+ add-on): app/mcp_server.py, Streamable HTTP at /mcp, spec 2025-11-25, `mcp>=1.23,<2`.
- Tests: `./run.sh test` (pytest, offline: LLM_PROVIDER=mock, BEE_MODE=demo). Every change keeps them green and adds a test.
- Run: `./run.sh` → http://127.0.0.1:8110 (`/`, `/family`, `/how`).
- Don't add dependencies without a reason; no frontend framework.
