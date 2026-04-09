# Onboarding

This document is the quick-start and orientation guide for a new agent or operator entering the UsefulHELPER project.

## Read Order

Read these in order:

1. `README.md`
2. `_docs/builder_constraint_contract.md`
3. `_docs/ARCHITECTURE.md`
4. `_docs/TOOLS.md`
5. `_docs/TODO.md`
6. `_docs/dev_log.md`
7. `_docs/TESTING.md`

## What UsefulHELPER Is

UsefulHELPER is a bounded MCP-style worker that acts as execution hands for a higher-level planning agent.

It is designed to:

- manipulate files only within one declared workspace root
- maintain a SQLite-backed sandbox `HEAD` and revision history under the project root
- maintain a SQLite-backed reusable parts catalog under the project root
- preserve continuity through a tasklist and journal
- help create its own next tools
- be vendored into apps as a local sidecar
- use local Ollama models only through explicit, structured tools
- expose a lightweight human-facing monitor over runtime events and logs

## Root Concepts You Must Understand

- `source_root`
  - the worker's code source location
- `project_root`
  - runtime logs, runtime DBs, sandbox storage, and builder-memory surfaces
- `workspace_root`
  - the only normal filesystem domain the tools may affect

If you misunderstand these roots, you will misunderstand the safety model.

## First Commands

From the project root:

```bat
setup_env.bat
python -m unittest discover -s tests -v
python -m compileall src tests
```

To run the worker directly:

```bat
run.bat --transport ndjson
```

## First Verification

After the worker is running, the normal first RPC flow is:

1. `initialize`
2. `tools/list`
3. `tools/call` with `capabilities.describe`
4. `tools/call` with `inference.describe_loops`

That tells you:

- the active server version
- the active roots
- the current tool set
- the active guardrails
- the active default inference loop

If you plan to use the sandbox workbench, the normal next calls are:

5. `tools/call` with `sandbox.init`
6. `tools/call` with `sandbox.ingest_workspace`
7. `tools/call` with `sandbox.query_symbols` or `sandbox.search_head`

If your source material arrives as a vendored bundle, insert:

- `tools/call` with `archive.inspect_zip`
- `tools/call` with `archive.extract_zip`

before sandbox ingestion.

If you already know the bundle should be normalized into sandbox `HEAD`, use:

- `tools/call` with `intake.zip_to_sandbox`

as the shorter default path.

Use the returned `bundle_summary` and `likely_entrypoints` before deeper reading when you want quick orientation on a new intake bundle.

If you want reusable local building blocks, the normal parts flow is:

- `tools/call` with `parts.catalog_build`
- `tools/call` with `parts.catalog_search`
- `tools/call` with `parts.catalog_get`
- `tools/call` with `parts.export_selection`

When using `parts.catalog_search`, steer the shelf on purpose:

- use `prefer_code` with `intent_target=structural` when you want implementation anchors
- use `prefer_docs` when you want operator-facing guidance
- use history terms like `journal` or `history` when you want log-style evidence instead of canonical docs

If you want a live operator view while the worker is active, launch:

- `run_monitor.bat`
- or `python -m src.app --ui monitor`

The monitor is read-only. It is useful for watching grouped activity lanes and inspecting recent inference/request history through the event ledger.

The monitor now also has a right-click helper:

- `Summarize` for panel or selected-text summaries
- `Ask About` for panel-aware questions
- `Settings` for per-action model and instruction tuning

The settings modal now refreshes local Ollama models into dropdowns, and the helper modals were tightened so they open near the cursor and keep their action buttons visible.

The helper is now stronger than a raw “send the panel to a model” flow:

- it first builds a structured monitor-context packet with parsed records and derived facts
- it answers some simple log/event questions mechanically before asking a model
- `Ask About` keeps a small sliding conversation window so follow-up questions can refer back to prior answers
- if a tiny model mostly repeats your question back, the helper will suggest trying a larger model instead of presenting the echo as an answer

For bounded repo awareness without raw shell:

- use `sysops.git_status` for branch and working-tree state
- use `sysops.git_diff_summary` for changed-file summaries
- use `sysops.git_repo_summary` for branch, HEAD, and dirty-state context
- use `sysops.git_recent_commits` for recent bounded history

## Canonical Memory Surfaces

The canonical continuity surfaces are:

- `_docs/_AppJOURNAL/CURRENT_TASKLIST.md`
- `_docs/_AppJOURNAL/BACKLOG.md`
- `_docs/_AppJOURNAL/entries/`
- `_docs/_journalDB/app_journal.sqlite3`

The mirror docs:

- `_docs/TODO.md`
- `_docs/dev_log.md`

are there to make onboarding easier, but the app journal remains the source of truth for meaningful recorded phases.

## Current Extension Workflow

When extending UsefulHELPER itself:

1. inspect current code with `ast.scan_python` or `fs.read_files`
2. if useful, ingest the relevant subset into sandbox `HEAD`
3. use `worker.create_tool_scaffold` for the next tool
4. implement the real logic in `src/core/components/extensions/`
5. run `worker.refresh_extension_tools`
6. test it through the real MCP route
7. promote it into a static route later if it no longer fits the extension lane
8. update tasklist and journal

## Vendored Sidecar Model

UsefulHELPER is designed to be exported into apps as `_sidecar/usefulhelper` or a similar app-local folder.

When vendored:

- the sidecar folder becomes its `project_root`
- the host app root becomes its `workspace_root`
- the vendored copy carries its own docs and launcher

## Current Priority Areas

- model policy defaults for local-model tasks now that the loop slot is in place
- bounded project-bootstrap and builder lanes on top of the loop slot
- bounded import, reference, and packaging tools distilled from `.possible-tools`
