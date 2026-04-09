# MindshardReferenceLibrary

Standalone reference-library tool for MindshardAGENT. It keeps imported reference material outside normal long-term memory, stores immutable revisions in a global library, and exposes explicit browse/search/read tools instead of auto-injecting content into prompts.

This package is **static-vendored**. All required source from the toolbox is copied into `vendor/library/`, and the app can be zipped, moved, or dropped into a new workspace without depending on the parent repo.

## What Is Here

```text
app.py
backend.py
mcp_server.py
settings.json
app_manifest.json
tool_manifest.json
CONTRACT.md
VENDORING.md
smoke_test.py
vendor/library/
lib/
examples/
```

## Core Behavior

- Global canonical store at `~/.mindshard_reference_library/`
- Immutable document revisions
- Nested hierarchy with `group`, `document`, and `blob` nodes
- Attached-scope search by default
- Explicit `scope=global` for whole-library search
- Session usage and excerpt caching without copying the whole library into the session DB
- Evidence Shelf mirroring for exact excerpts
- Content-addressed payload storage to keep repeated imports cheap

## Deduplication

The package uses content-addressed storage backed by the vendored `Blake3HashMS` service.

- Normalized text payloads are stored once by hash under `content/text/`
- Binary payloads are stored once by hash under `content/blobs/`
- Re-importing identical content reuses the stored payload bytes
- Excerpt reads get a stable `operation_id` and excerpt hash so retries stay duplicate-safe

`Blake3HashMS` uses SHA3-256 when native `blake3` is not installed, which keeps the package portable and dependency-light.

## Provider Adapters

This package does not implement parsing engines from scratch. It adapts vendored toolbox parts behind a normalized contract:

- `python_provider`
  - wraps vendored `PythonChunkerMS`
  - used for `.py`
- `microservice_provider`
  - wraps vendored `TextChunkerMS.chunk_by_paragraphs`
  - used for prose-like readable docs
- `microservice_provider`
  - wraps vendored `TextChunkerMS.chunk_by_lines`
  - used as the fallback chunker for readable text

Unsupported binaries are imported as blobs with metadata only.

## Agent Tools

- `library_manifest`
- `library_import`
- `library_refresh`
- `library_archive`
- `library_rename`
- `library_move`
- `library_attach`
- `library_detach`
- `library_list_roots`
- `library_list_children`
- `library_search`
- `library_get_detail`
- `library_list_revisions`
- `library_read_excerpt`
- `library_export`

The MCP server exposes the same tool names and semantics.

## Storage Layout

Global library root:

```text
~/.mindshard_reference_library/
  library_manifest.json
  providers_manifest.json
  library_index.sqlite3
  operations.jsonl
  content/
    text/
    blobs/
  records/
    nodes/
    revisions/
    temporal_chain.sqlite3
  exports/
```

Project-local attachment truth:

```text
.mindshard/state/reference_library_attachments.json
```

Session-local truth:

- `library_usage`
- `library_excerpt_cache`

## Quick Start

Run the self-test:

```powershell
python smoke_test.py
```

Check health:

```powershell
python app.py --health
```

Start MCP:

```powershell
python mcp_server.py
```

## Python Example

```python
from backend import BackendRuntime

rt = BackendRuntime()

imported = rt.call(
    "MindshardReferenceLibrary",
    "library_import",
    source_path="C:/docs/reference-folder",
    project_path="C:/work/my-project",
    attach=True,
    attachment_context={"reason": "bootstrap"},
)

hits = rt.call(
    "MindshardReferenceLibrary",
    "library_search",
    query="adapter registry",
    project_path="C:/work/my-project",
)
```

## Notes

- `library_search` is intentionally conservative: attached scope is the default.
- `library_read_excerpt` records exact provenance by `revision_id`, not just current node state.
- This v1 package is headless. Build a UI client later over the same contracts if needed.
