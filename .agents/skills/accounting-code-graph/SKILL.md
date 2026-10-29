---
name: accounting-code-graph
description: Use the local Graphify code map to trace AI Accounting Office backend API, Application Service, Repository, ledger, Agent Tool Registry, and MCP relationships during development or review.
---

Use this skill when a task needs a code-structure map. The graph is a navigation aid; verify each conclusion in the actual source.

1. Run `python scripts/dev_code_graph.py status`. If no graph exists or the relevant code changed, run `python scripts/dev_code_graph.py rebuild`. This rebuild reads only tracked Python files under `backend/app/` and `backend/migrations/versions/`; it does not read `.env`, accounting data, or the local Design SSOT folder.
2. Run `python scripts/dev_code_graph.py explain ToolRegistry`, `query "journal ledger"`, or `path "A" "B"` as needed. For a broad query, narrow to a symbol or file rather than treating truncated output as a complete answer.
3. Open the referenced source files and confirm imports, permissions, UoW boundaries, and call sites. Graphify `INFERRED` edges are hypotheses.
4. Graphify must be installed separately in a local environment. Set `GRAPHIFY_EXE` to its executable if it is not on PATH. In another worktree, `GRAPHIFY_GRAPH` can point to an existing graph; rebuild after relevant code changes. The script writes only to ignored `.local/code-graph/`. No automatic hooks, external model calls, or product DB connections are part of this skill.
