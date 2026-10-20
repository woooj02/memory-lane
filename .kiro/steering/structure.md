---
inclusion: always
---
# Structure

- app/config.py: all settings, from the environment (.env is loaded by run.sh)
- app/bee.py: Bee sources (CliBee real, DemoBee sample day), transcript and time helpers
- app/digest.py: conversation → speakers, cards, promises, English lines
- app/llm.py: the AI engines
- app/store.py: SQLite schema + MIGRATIONS (append a migration; never edit an old one)
- app/service.py: MemoryLane: sync, practice plan, spacing, approvals, promises, live feed
- app/mcp_server.py: MCP tools; every tool returns a `say` line in the parent's language
- app/main.py: HTTP routes
- web/index.html: evening screen (Echo Show, 1280×800, must fit without scrolling)
- web/family.html, web/how.html: family page, pipeline page
- fixtures/: sample day (demo_day.json) and hand-written digests (demo_digests.json)
- tests/test_app.py: one file, plain pytest functions
