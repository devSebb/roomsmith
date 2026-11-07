# Changelog

## 0.1.0 (in progress)

Built 2026-11-07, hackathon week.

- Engine (`rs_core`): scene model, 17 operations with relational placement,
  hard validation and soft issues, fit checks, SQLite store with full-snapshot
  revisions, undo/redo, idempotent commands, cross-process write transaction,
  product dimension parsing, draft→scene layout builder, GLB export.
- Agent half: nine `room_studio_*` tools, `/room`, `room-design` skill,
  `pre_llm_call` awareness hook; photo reading through `ctx.llm` with a fallback
  ladder.
- Dashboard backend: FastAPI routes incl. long-poll `wait` and base64 export.
- Editor: three.js 3D/plan editor with snapping, live revisions, inspectors,
  calibration, products, fit questions, exports; Desktop and dashboard shells.
- Verified on Hermes 0.21.0: `hermes plugins doctor --ci`, dashboard tab live.
