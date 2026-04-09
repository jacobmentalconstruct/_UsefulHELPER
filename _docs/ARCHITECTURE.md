# UsefulHELPER Architecture

## Purpose

UsefulHELPER is a constrained MCP-style worker designed to act as mechanical execution hands for a higher-level planning agent.

The current worker supports deterministic tooling, a SQLite-backed sandbox workbench, self-extension scaffolding, vendored sidecar export, a lightweight Tkinter operator monitor, and bounded local-model inference through explicit tool routes.

## Composition Root

- `src/app.py`
  - process entry point
  - binds the worker project root and the session workspace root
  - starts the core runtime engine

## Runtime Flow

1. `src/app.py` starts the application engine.
2. `src/core/runtime/mcp_server.py` reads JSON-RPC messages over either NDJSON or Content-Length framing.
3. the server dispatches requests into `src/core/orchestrators/mcp_orchestrator.py`
4. the orchestrator handles protocol methods and routes tool calls to bounded managers
5. managers delegate to single-domain components
6. successful runtime dispatches are logged to the local SQLite event ledger

## Ownership Map

- `src/core/orchestrators/`
  - JSON-RPC and MCP request coordination

- `src/core/managers/workspace_manager.py`
  - bounded coordination for archive, filesystem, parts-catalog, sandbox, scaffolding, and AST tools

- `src/core/components/archive_component.py`
  - bounded archive inspection and extraction behavior

- `src/core/components/intake_component.py`
  - bounded bundle-intake coordination from archive extraction into sandbox `HEAD`

- `src/core/components/parts_catalog_component.py`
  - reusable local parts catalog behavior

- `src/core/managers/memory_manager.py`
  - bounded coordination for tasklist and journal tools

- `src/core/managers/inference_manager.py`
  - bounded coordination for local-model inference tools

- `src/core/components/filesystem_component.py`
  - relative-path-only workspace filesystem operations

- `src/core/components/scaffold_component.py`
  - manifest scaffolding and self-tool scaffold generation

- `src/core/components/ast_component.py`
  - Python AST structural scanning

- `src/core/components/sandbox_component.py`
  - bounded project sandbox workbench behavior

- `src/core/components/builder_memory_component.py`
  - app journal and tasklist operations

- `src/core/components/capability_component.py`
  - worker self-description

- `src/core/components/extension_tool_component.py`
  - validated extension-tool refresh and bounded generic dispatch

- `src/core/components/extensions/ollama_chat_json_component.py`
  - model inventory helper behavior and compatibility surface for the Ollama lane

- `src/core/components/extensions/ollama_inference_loop_cartridge.py`
  - reusable single-turn Ollama loop cartridge plugged into the inference slot

- `src/core/services/inference_loop_service.py`
  - loop-cartridge registration, default slot ownership, and normalized inference-request building

- `src/core/services/ollama_service.py`
  - local HTTP client for the Ollama API

- `src/core/services/archive_service.py`
  - `.zip` inspection and extraction with zip-slip protection

- `src/core/services/archive_intake_service.py`
  - one-call archive inspection, extraction, sandbox ingestion, and bundle-summary inference

- `src/core/services/extension_tool_service.py`
  - blueprint validation, extension-module reload, and hot-load registration support

- `src/core/services/sysops_service.py`
  - allowlisted read-only git wrappers with graceful non-repo handling

- `src/core/services/parts_catalog_store.py`
  - SQLite-backed reusable parts catalog with content blobs, metadata, symbols, intent-aware evidence-shelf search, and export

- `src/core/services/sandbox_store.py`
  - SQLite-backed HEAD, revisions, diffs, exports, and Python symbol index

- `src/ui/adapters/runtime_monitor_adapter.py`
  - read-only snapshot adapter over the runtime event ledger and app log

- `src/ui/components/monitor_window.py`
  - Tkinter operator window with grouped activity tabs, event detail, and right-click helper actions

- `src/ui/helpers/monitor_helper_service.py`
  - structured monitor-context packet building, mechanical-first monitor answers, sliding conversation memory, prompt-echo safety, and local-model helper logic for summaries and contextual questions

- `src/ui/helpers/monitor_settings_store.py`
  - persisted model/instruction settings for the monitor helper actions

- `src/ui/managers/ui_manager.py`
  - UI-only coordination for the startup banner and operator monitor

## Guardrails

- one explicit workspace root per process session
- no tool-level override of the workspace root
- no absolute paths in tool arguments
- all paths are resolved relative to the bound workspace root
- no raw shell tool in tranche 1
- journal and tasklist memory stay under the worker project `_docs/` surfaces
- sandbox state lives under the worker project `data/sandbox/` surface
- parts-catalog state lives under the worker project `data/parts/` surface
- sandbox export still writes only under the active workspace root

## Sandbox Workbench

UsefulHELPER now has a typed internal sandbox layer:

- `content_blobs`
  - immutable deduplicated text content by hash
- `file_head`
  - current materialized HEAD state for each sandboxed file
- `file_revisions`
  - immutable revision chain with diff text and provenance
- `symbol_index`
  - Python symbol records keyed by current HEAD revisions
- `exports`
  - materialization records for sandbox-to-folder export operations

The intended flow is:

1. ingest bounded workspace files into sandbox HEAD
2. read/search/query symbols from the sandbox for cheaper reasoning
3. stage structured diffs against sandbox HEAD
4. export sandbox HEAD back into a bounded workspace folder
5. test, vendor, or continue iterating

This keeps the real workspace tree as the execution surface while giving the worker a lower-friction internal reasoning substrate.

Archive intake fits ahead of sandbox ingest when the source material arrives as a vendored bundle:

1. inspect the bundle with `archive.inspect_zip`
2. extract the bundle with `archive.extract_zip`
3. ingest the extracted tree into sandbox HEAD

UsefulHELPER now also exposes the one-call lane:

1. call `intake.zip_to_sandbox`
2. inspect the returned bundle summary, entrypoint hints, extraction, and ingestion records
3. continue with `sandbox.read_head`, `sandbox.search_head`, or `sandbox.query_symbols`

## Evidence Shelf Retrieval

The parts shelf is meant to support recall, not just keyword lookup.

Search behavior blends:

- SQLite FTS relevance
- token-aware matching across path, symbols, summary, and content
- intent targeting such as `structural`, `verbatim`, `semantic`, and `relational`
- evidence-lane steering through `prefer_code` and `prefer_docs`
- document-role weighting so canonical docs surface ahead of historical journal noise unless the query explicitly asks for history

Returned evidence includes:

- a shelf-level summary
- a stable location list
- structured location records with document roles
- per-item summaries and `why_matched` reasons

## Self-Extension Path

The worker is meant to help create its own next tool.

Tranche 1 supports this through:

- `fs.write_files`
- `fs.patch_text`
- `project.scaffold_from_manifest`
- `worker.create_tool_scaffold`
- `worker.refresh_extension_tools`

The dedicated tool scaffold generator creates component, test, and blueprint stubs for the next worker tool while preserving bounded ownership.

The sandbox workbench extends that path by letting the worker stage and inspect candidate edits before exporting them back to the live folder tree.

UsefulHELPER now also supports a guarded extension refresh lane:

1. generate or update a blueprint under `_docs/tool_blueprints/`
2. implement the component under `src/core/components/extensions/`
3. run `worker.refresh_extension_tools`
4. invoke the extension tool through the normal MCP tool surface

This path is intentionally constrained:

- extension blueprints cannot override static tool names
- only extension-package modules are loadable
- only `workspace` and `memory` manager lanes are hot-loadable in the current tranche

## Local Inference

The worker now exposes a reusable inference loop slot instead of a single hardwired inference path.

Current inference shape:

- `InferenceManager` owns the bounded inference lane
- `InferenceLoopService` owns cartridge registration and the active default slot
- `OllamaSingleTurnLoopCartridge` is the current default cartridge under `ollama.single_turn`
- `ollama.chat_json` and `ollama.chat_text` both route through that slot
- `ollama.list_models` remains a direct bounded inventory helper

Inference rules:

- local Ollama only in the current tranche
- explicit tool call required
- no autonomous agent loop inside the worker
- inference cartridges stay separate from workspace file authority
- swapping or adding loops should happen by registering another cartridge instead of rewriting manager logic

## Vendored Sidecar Export

The worker can export a lean copy of itself into a target app folder under the current workspace root.

Sidecar export rules:

- read from the worker's own `source_root`
- write only under the active workspace root
- produce a launcher that binds the sidecar's workspace root to the host app root
- exclude volatile runtime state and builder-memory databases from the export
- preview managed create/update/stale-file diffs before a reinstall write
- allow overwrite-style reinstall only for recognized UsefulHELPER sidecar targets
- preserve unmanaged files already present inside a recognized sidecar target

## Operator Monitor

UsefulHELPER now also has a lightweight human-facing operator monitor.

Monitor rules:

- read-only against the worker runtime SQLite ledger and app log
- grouped recent activity instead of one panel per tool
- selected-event inspection shows payload and response detail
- right-click helper actions can summarize the current context, answer follow-up questions, or edit helper settings
- helper requests are grounded on structured monitor-context packets instead of raw panel text alone
- simple log/event requests can be handled mechanically before the model is consulted
- ask-about follow-ups keep a small sliding conversation window with summarized falloff
- prompt-echo failures degrade into a larger-model suggestion instead of being shown as valid answers
- intended as a sidecar operator view that can run separately from the MCP serve loop

## Explicit Non-Goals

- no unrestricted shell execution
- no multi-root writes in a single session
- no autonomous Ollama-backed planner loop yet
