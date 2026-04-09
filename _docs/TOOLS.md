# Tool Catalog

## Session Guardrails

- all tool paths are relative to the startup-declared workspace root
- absolute paths are rejected
- tool effects are bounded to one workspace root per process session

## Built-In Tools

- `capabilities.describe`
  - reports worker metadata, tool names, and current guardrail status

- `archive.inspect_zip`
  - inspects a bounded `.zip` archive
  - reports normalized entry paths and flags unsafe members before extraction

- `archive.extract_zip`
  - extracts a bounded `.zip` archive into a target workspace folder
  - rejects archives with unsafe paths and guards against zip-slip behavior

- `intake.zip_to_sandbox`
  - inspects a bounded `.zip`, extracts it into a bounded workspace folder, and ingests that tree into sandbox `HEAD`
  - returns the chained inspection, extraction, and sandbox-ingestion records in one structured payload
  - also returns `bundle_summary` and `likely_entrypoints` inferred from manifests and common entry filenames

- `parts.catalog_build`
  - builds or rebuilds the local SQLite parts catalog from bounded source trees
  - stores state under `data/parts/parts_catalog.sqlite3`

- `parts.catalog_search`
  - searches the parts catalog with SQLite FTS-backed and token-aware ranked matching
  - scores path, name, kind/layer, symbols, summary, content, document role, and FTS relevance
  - supports `intent_target`, `prefer_code`, and `prefer_docs` to steer the returned shelf
  - returns an evidence shelf with `shelf_summary`, `location_index`, `location_records`, and per-item summaries

- `parts.catalog_get`
  - reads one or more catalog parts with metadata, content, and indexed symbols

- `parts.export_selection`
  - exports selected catalog parts back into a bounded workspace folder
  - preserves original relative paths from the catalog

- `fs.list_tree`
  - lists files and directories under a relative workspace path

- `fs.make_tree`
  - creates directories under the workspace root

- `fs.read_files`
  - reads UTF-8 files from the workspace root

- `fs.write_files`
  - writes UTF-8 files from structured JSON input

- `fs.patch_text`
  - performs structured replace/append/prepend text operations

- `fs.search_text`
  - searches UTF-8 files under the workspace root with regex support
  - returns relative path, line number, and matched line text

- `project.scaffold_from_manifest`
  - creates directory trees and boilerplate files from a manifest

- `worker.create_tool_scaffold`
  - generates a new worker-tool component stub, test stub, and blueprint doc

- `worker.refresh_extension_tools`
  - reloads validated extension blueprints from `_docs/tool_blueprints/`
  - hot-loads tools implemented under `src/core/components/extensions`
  - skips disabled manifests, invalid manifests, and static tool-name conflicts

- `sidecar.export_bundle`
  - previews or exports a lean vendorable UsefulHELPER sidecar into a target app folder
  - reads from the worker source tree but writes only under the current workspace root
  - returns managed diff reporting for reinstall review through `dry_run=true`
  - requires `overwrite=true` and `reinstall=true` before applying changes to an existing recognized sidecar target
  - generates `run_for_app.bat`, `sidecar_manifest.json`, and `_docs/SIDECAR.md`

- `ast.scan_python`
  - scans Python source with the standard-library `ast` module

- `sandbox.init`
  - initializes or resets the SQLite-backed sandbox workbench
  - stores state under `data/sandbox/project_sandbox.sqlite3`

- `sandbox.ingest_workspace`
  - ingests bounded workspace files into sandbox `HEAD` and immutable revision history
  - skips obvious runtime/database byproducts and binary files

- `sandbox.read_head`
  - reads files from sandbox `HEAD` instead of the live workspace tree

- `sandbox.search_head`
  - searches sandbox `HEAD` contents with regex support
  - useful when the worker should reason over the normalized sandbox instead of rereading files

- `sandbox.stage_diff`
  - applies structured text edits to sandbox `HEAD`
  - records immutable revisions and unified diff history

- `sandbox.export_head`
  - materializes sandbox `HEAD` back into a bounded workspace folder
  - useful for testing, vendoring, or inspection before touching a target tree directly

- `sandbox.history_for_file`
  - returns the current sandbox `HEAD` metadata and recent revision history for one file

- `sandbox.query_symbols`
  - returns Python import/class/function symbol records from current sandbox `HEAD`

- `python.run_unittest`
  - runs allowlisted `python -m unittest discover` inside the workspace root
  - returns structured command, exit code, stdout, stderr, and success flag

- `python.run_compileall`
  - runs allowlisted `python -m compileall` inside the workspace root
  - returns structured command, exit code, stdout, stderr, and success flag

- `sysops.git_status`
  - runs a read-only allowlisted git status summary inside the workspace root
  - reports gracefully when git is unavailable or the target path is not a git repo

- `sysops.git_diff_summary`
  - runs a read-only allowlisted git diff summary inside the workspace root
  - supports staged diff summaries through `cached=true`

- `sysops.git_repo_summary`
  - reads a bounded git repo summary with branch, HEAD commit metadata, and dirty-file counts
  - reports gracefully when the target path is not a git repo

- `sysops.git_recent_commits`
  - reads a bounded recent git commit list from a requested ref
  - returns structured commit metadata and graceful non-repo results

- `inference.describe_loops`
  - reports the registered inference loop cartridges and the active default loop slot

- `ollama.chat_json`
  - runs the active or requested inference loop cartridge and returns a parsed JSON object
  - bounded to explicit prompts and structured output

- `ollama.chat_text`
  - runs the active or requested inference loop cartridge and returns text
  - useful when the higher-level agent needs cheap bounded prose instead of JSON

- `ollama.list_models`
  - queries the local Ollama service for currently available models
  - useful for model routing checks before inference calls

- `journal.append`
  - appends an execution-phase record to the app journal database and mirror markdown

- `tasklist.replace`
  - replaces the current bounded tasklist

- `tasklist.view`
  - reads the current tasklist state

## Operator Surfaces

- `run_monitor.bat`
  - launches the lightweight Tkinter operator monitor against the current worker project root

- `python -m src.app --ui monitor`
  - launches the same monitor directly without the batch wrapper
  - reads the runtime event ledger and app log only
  - groups activity into request, workspace, execution, inference, memory, and other tabs
  - adds right-click helper actions for `Summarize`, `Ask About`, and `Settings`
  - helper settings now use refreshable Ollama-model dropdowns and context-aware fallback answers
  - helper requests are grounded on structured monitor-context packets with parsed records and derived facts
  - simple log-listing and event-explanation questions can be answered mechanically before the model is consulted
  - `Ask About` keeps a small sliding conversation window with summarized falloff for follow-up questions
  - prompt-echo answers are replaced with a suggestion to try a larger model

## Future Tooling Direction

- model policy defaults and routing profiles for local-model tasks
- import and reference-oriented tool packs inspired by `.possible-tools/`
- deeper sandbox integration with reference-library and cartridge-style ingest patterns
