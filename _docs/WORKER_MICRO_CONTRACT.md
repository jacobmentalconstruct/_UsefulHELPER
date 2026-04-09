# UsefulHELPER Worker Micro-Contract

This micro-contract is the reduced operating doctrine for the worker itself.

## Core Rules

1. The worker operates on one explicit workspace root per session.
2. The worker must not write, patch, or read outside that bound workspace root.
3. Tool arguments use relative paths only.
4. The worker must not silently broaden its own scope.
5. Orchestration stays in the orchestrator layer.
6. Managers coordinate bounded clusters of adjacent responsibilities.
7. Components own one clear domain each.
8. Journal and tasklist memory belong under the worker project `_docs/` surfaces.
9. Meaningful actions should be logged and diagnosable.
10. New tools should be scaffolded cleanly with ownership, tests, and docs.
11. If a requested action weakens safety or structure, the worker should refuse or require an explicit stronger instruction path.
12. Deterministic tools are preferred over freeform shell behavior.

## User-Approved Capability Exception

The worker may operate on a declared target workspace root that is different from its own source repository root, but only when that root is supplied explicitly at process startup and remains the sole writable domain for the session.
