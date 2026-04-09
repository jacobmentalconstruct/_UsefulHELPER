# Testing

## Main Verification Commands

```bat
python -m unittest discover -s tests -v
python -m src.app --transport ndjson
python -m src.app --transport content-length
```

## Current Coverage

- transport round-trips for NDJSON and Content-Length framing
- JSON-RPC initialize and tools calls
- bounded archive inspection and zip-slip-safe extraction
- one-call archive inspection, extraction, and sandbox ingestion
- manifest-aware bundle summaries and likely entrypoint hints on the one-call intake lane
- extension-tool refresh and hot-reload through the real MCP surface
- allowlisted git sysops wrappers, including non-repo handling
- bounded repo-summary and recent-commit wrappers
- parts catalog build, ranked search, evidence-shelf shaping, inspection, and export
- workspace filesystem operations
- sandbox ingest, HEAD reads, diff staging, history, symbol query, and export flow
- relative-path-only guardrail enforcement
- tasklist and journal behavior
- self-tool scaffold generation
- vendored sidecar export and re-launch
- sidecar dry-run diff reporting, guarded reinstall, and non-sidecar overwrite rejection
- runtime-monitor adapter snapshot grouping and app-log tail reads
- monitor helper settings persistence and helper-service prompt construction
- monitor helper fallback-answer behavior for empty model replies
- monitor helper structured-context packet parsing for log panels and detail panels
- monitor helper mechanical-first answers for log enumeration and event explanation
- monitor helper sliding conversation-window summarization
- monitor helper prompt-echo fallback to a larger-model recommendation
- reusable inference loop-slot coverage and default-cartridge reporting
- local Ollama JSON inference through the worker tool path
- local Ollama text inference through the worker tool path
- local Ollama model inventory through the worker tool path

## Test Approach

The end-to-end tests spawn the worker as a subprocess and talk to it over stdin/stdout using both framing styles.

Temporary project roots and workspace roots are created inside `data/test_workspaces/` so verification stays bounded to the repository.

The Tkinter operator monitor was also smoke-booted locally against the live runtime DB and log to confirm the window can open, poll, render once, and close cleanly on this machine.

The catalog round-trip coverage now also checks:

- evidence-shelf fields like `shelf_summary`, `location_index`, and `location_records`
- code-first versus docs-first ranking behavior
- canonical-doc preference over journal entries unless the query asks for history
- extension refresh picks up newly scaffolded tools and code updates without a process restart
