# Development Log

This file is a human-readable mirror of meaningful project phases.

Canonical detailed continuity still lives under:

- `_docs/_AppJOURNAL/entries/`
- `_docs/_journalDB/app_journal.sqlite3`

## 2026-04-07

### Worker bootstrap

- Bootstrapped the dual-transport worker and established the initial tool spine.
- Added bounded filesystem tools, AST scanning, tasklist handling, and journal handling.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-07_225245_20260407-225245-e57d32ae.md`

### Vendored sidecar export

- Added `sidecar.export_bundle`.
- Verified that a vendored copy can boot and operate inside a host app root.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-07_230301_20260407-230301-6973f17e.md`

### Local Ollama inference

- Implemented `ollama.chat_json` as a routed inference tool.
- Added live end-to-end verification through the worker's MCP path.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-07_230749_20260407-230749-a10f520e.md`

### README and docs strengthening

- Expanded `README.md` into a real operator guide.
- Strengthened the docs with onboarding, troubleshooting, and sidecar guidance.
- Journal mirrors:
  - `_docs/_AppJOURNAL/entries/2026-04-07_230918_20260407-230918-c8ab3f7f.md`
  - `_docs/_AppJOURNAL/entries/2026-04-07_231222_20260407-231222-46323924.md`

### Documentation hardening for vendorable sidecars

- Cleaned stale wording from the live docs and refreshed the canonical current tasklist.
- Added project-local onboarding, TODO, and dev-log mirror docs.
- Copied the governing builder contract into the project docs and expanded sidecar export so vendored bundles carry the fuller doc set.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-07_232554_20260407-232554-fe5d2ec3.md`

### Useful tool expansion and self-use against `.possible-tools`

- Added `fs.search_text`, `python.run_unittest`, `python.run_compileall`, and `ollama.list_models`.
- Extended the routed MCP surface and round-trip coverage so the new tools work through real NDJSON and Content-Length sessions.
- Used the worker against its own `.possible-tools/` examples to shortlist future import, reference-library, and packaging-oriented tool packs.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-07_233949_20260407-233949-d6cb9247.md`

## 2026-04-08

### Sandbox workbench tranche

- Added a SQLite-backed sandbox workbench with immutable content blobs, current `HEAD`, revision history, diff staging, export tracking, and Python symbol indexing.
- Routed the sandbox tool set through the live MCP surface: `sandbox.init`, `sandbox.ingest_workspace`, `sandbox.read_head`, `sandbox.search_head`, `sandbox.stage_diff`, `sandbox.export_head`, `sandbox.history_for_file`, and `sandbox.query_symbols`.
- Verified the new flow through subprocess round trips and a live self-use pass against the UsefulHELPER repo.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_000933_20260408-000933-aebfc046.md`

### Archive intake tooling and sandbox integration

- Added `archive.inspect_zip` and `archive.extract_zip` with zip-slip protection.
- Verified safe extraction and unsafe-path rejection through worker round-trip tests.
- Used the worker to inspect and extract the real `.possible-tools/BDNeuralTranslation_ToolKit/CASStack.zip` bundle, then ingested the extracted tree into sandbox `HEAD` and queried it there.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_003513_20260408-003513-e6676677.md`

### Reusable parts shelf and ranked catalog search

- Added a SQLite-backed reusable parts catalog with build, search, inspect, and export flows.
- Tightened catalog retrieval so multi-word queries use SQLite FTS-backed and token-aware ranked matching across path, name, kind/layer, symbols, summary, and content.
- Verified the original live failure case: `sidecar export bundle` now returns ranked results with `src/core/components/sidecar_component.py` at the top.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_024807_20260408-024807-eb87c93a.md`

### FTS retrieval upgrade for the parts shelf

- Confirmed local SQLite FTS5 support and wired an FTS index into catalog builds.
- Blended FTS relevance with the ranked token matcher so search results now carry both `score` and `fts_rank` evidence.
- Re-ran the live `sidecar export bundle` case and confirmed the expected sidecar component result with explicit FTS support in the payload.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_025539_20260408-025539-766425c9.md`

### Evidence shelf polish for catalog search

- Upgraded `parts.catalog_search` to return a richer evidence shelf with `shelf_summary`, `location_index`, `items`, per-item summaries, and `why_matched` reasons.
- Cleaned anchor-symbol selection so code entries prefer class/function anchors instead of import noise.
- Rechecked the live `sidecar export bundle` shelf and confirmed the top item now anchors cleanly on `SidecarComponent`.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_031718_20260408-031718-78a542f1.md`

### Evidence-shelf steering and canonical-doc weighting

- Extended `parts.catalog_search` with `intent_target`, `prefer_code`, and `prefer_docs` so the same semantic query can be steered toward structural code evidence or operator-facing docs.
- Added `document_role` and `location_records` so evidence shelves carry stronger location metadata and clearer per-item grounding.
- Tuned document-role weighting so docs-first searches favor canonical docs like `README.md` and `_docs/ARCHITECTURE.md`, while history-flavored searches can pivot toward `_docs/dev_log.md` and journal evidence.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_070617_20260408-070617-696335ae.md`

### One-call archive-to-sandbox intake

- Added `intake.zip_to_sandbox` so bundle intake can run as one bounded call instead of separate inspect, extract, and ingest steps.
- Verified the new route through subprocess round trips and a live dogfood run against `.possible-tools/BDNeuralTranslation_ToolKit/CASStack.zip`.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_073720_20260408-073720-9e695109.md`

### Manifest-aware intake summaries and entrypoint hints

- Extended `intake.zip_to_sandbox` so one-call bundle intake now returns `bundle_summary` and `likely_entrypoints`.
- Verified the real CASStack bundle now yields top-level bundle structure, summary-file detection, parsed manifest metadata, and likely MCP/app/backend/UI entry files.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_074326_20260408-074326-dde1a7dc.md`

### Guarded extension refresh and hot-reload

- Added `worker.refresh_extension_tools` so validated extension blueprints can be hot-loaded without a full worker restart.
- Added a bounded generic dispatch lane for extension tools under `src/core/components/extensions`.
- Verified live that a temporary extension tool could be scaffolded, refreshed into the tool list, invoked, edited, refreshed again, and re-invoked with changed behavior.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_080026_20260408-080026-616a76c3.md`

### Initial allowlisted sysops wrappers

- Added `sysops.git_status` and `sysops.git_diff_summary` as read-only bounded Git wrappers.
- Verified round-trip behavior both for repo-aware paths and for graceful non-repo handling.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_080501_20260408-080501-0a918ab9.md`

### Expanded allowlisted git wrappers

- Added `sysops.git_repo_summary` and `sysops.git_recent_commits` as additional read-only Git planning helpers.
- Verified repo-aware behavior in the round-trip suite and graceful non-repo reporting on the live UsefulHELPER workspace.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_083017_20260408-083017-07478ae0.md`

### Parking pass after sysops completion

- Closed the active sysops tranche and normalized the task mirrors so `CURRENT_TASKLIST.md`, `TODO.md`, and onboarding priorities all agree.
- Removed stale roadmap language that still treated hot-reload and allowlisted Git wrappers as future work.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_083924_20260408-083924-be2e680f.md`

### Sidecar reinstall diff reporting and day-end parking

- Extended `sidecar.export_bundle` with `dry_run=true` diff preview, recognized-sidecar detection, guarded reinstall semantics, and preserved unmanaged-file reporting.
- Verified the new lane through round-trip coverage, a live sidecar preview/apply dogfood pass, and updated the docs/task mirrors so the next item is now model policy defaults.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_085843_20260408-085843-9cadcff6.md`

### Lightweight operator monitor and final day-end parking

- Added a lightweight Tkinter monitor over the runtime event ledger and app log, with grouped request/workspace/execution/inference/memory tabs and selected-event detail.
- Added a monitor launcher (`run_monitor.bat`), verified the adapter and GUI bootstrap path, and parked the repo again with the docs/task mirrors aligned on model policy defaults as the next item.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_091337_20260408-091337-535504fd.md`

### Monitor helper actions and re-park

- Added right-click `Summarize`, `Ask About`, and `Settings` actions to the operator monitor with local-model helper calls and persisted per-action settings.
- Verified the helper settings store, helper prompt wiring, and full test suite, then updated the docs/task mirrors so the next item still remains model policy defaults.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_094405_20260408-094405-88dd5ea2.md`

### Monitor helper polish after live feedback

- Replaced free-text helper model entry with refreshable Ollama-model dropdowns, improved empty-response fallback handling, and tightened the modal placement/layout behavior.
- Re-ran the full test suite and compile checks, then synchronized the docs and task mirror one final time before parking.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-08_102750_20260408-102750-1ca4f6ef.md`

## 2026-04-09

### Reusable inference loop cartridge and loop slot

- Added a reusable inference loop architecture with `InferenceLoopService`, normalized loop request/result models, and a default `ollama.single_turn` cartridge.
- Routed `ollama.chat_json` and the new `ollama.chat_text` tool through the manager-owned loop slot, and added `inference.describe_loops` so the active cartridge can be inspected explicitly.
- Verified the tranche with compile checks, unit coverage for the loop service, and full worker round-trip coverage including the new loop-slot surface.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-09_090309_20260409-090309-b7f3a1d2.md`

### Monitor helper grounding, memory, and echo safety

- Reworked the operator helper so `Summarize` and `Ask About` run on structured monitor-context packets instead of loose raw text.
- Added mechanical-first answers for simple log enumeration and event-explanation questions, a sliding conversation window with summarized falloff for follow-up questions, and per-modal model selection with rerun support.
- Added prompt-echo detection so tiny-model “repeat the prompt back” failures now degrade into a clear recommendation to try a larger model instead of presenting the echo as an answer.
- Verified the tranche with targeted monitor-helper tests plus the full suite.
- Journal mirror: `_docs/_AppJOURNAL/entries/2026-04-09_103903_20260409-103903-29567a59.md`
