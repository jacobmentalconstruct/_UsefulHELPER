# Backlog

- Add controlled hot-reload for newly scaffolded tool modules.
- Add allowlisted sysops wrapper tools only after the deterministic boundary is well tested.
- Add Ollama-backed planning helpers only after deterministic tool use is stable.

## 2026-04-07T22:52:45.187927-05:00 | Tranche 1 worker bootstrap and self-extension handoff

- Wire the generated ollama.chat_json stub into the orchestrator and workspace manager when tranche 2 begins.
- Evaluate controlled hot-reload for newly scaffolded tools.

## 2026-04-07T23:03:01.252874-05:00 | Vendored sidecar export verified live

- Implement ollama.chat_json as the first routed local-model helper.
- Consider sidecar overwrite diff reporting for repeated exports.

## 2026-04-07T23:07:49.486767-05:00 | Ollama tool activated and used for tranche guidance

- Tune hot-reload or manifest-refresh for self-generated tools.
- Consider model policy defaults for 0.5b, 4b, 7b, and 9b tasks.

## 2026-04-07T23:09:18.348066-05:00 | README expanded into operator guide

- Keep the README aligned with future hot-reload and sysops-wrapper tranches.

## 2026-04-07T23:12:22.621047-05:00 | README strengthened with operations guidance

- Keep README operational guidance aligned with future hot-reload and allowlisted sysops tranches.

## 2026-04-07T23:25:54.066513-05:00 | Documentation set hardened for vendorable sidecars

- Keep doc mirrors synchronized as future hot-reload and sysops-wrapper tranches land.

## 2026-04-07T23:39:49.179968-05:00 | Useful tool expansion and self-use pass

- Distill the best reusable patterns from .possible-tools into bounded import, reference-library, and packaging tool packs.
- Consider an archive extraction tool for studying vendored zip packages inside the workspace root.

## 2026-04-08T00:09:33.181846-05:00 | Sandbox workbench tranche with HEAD, revisions, and export flow

- Add deeper cartridge/CAS-backed ingest modes and archive tooling for project intake.
- Consider sandbox-to-workspace diff reporting before export overwrites existing files.

## 2026-04-08T00:35:13.255928-05:00 | Archive intake tooling with zip-slip protection

- Add archive-aware sandbox ingest helpers so bundle extraction and sandbox ingestion can be chained with fewer calls.
- Consider manifest-aware zip inspection to surface likely app entrypoints before extraction.

## 2026-04-08T02:48:07.577896-05:00 | Reusable parts shelf and ranked catalog retrieval

- Consider SQLite FTS-backed catalog search once the current ranked token matcher stabilizes in more live usage.
- Add recipe-level catalog exports so multiple parts can be assembled as named bundles.

## 2026-04-08T02:55:39.751173-05:00 | FTS-backed parts catalog retrieval upgrade

- Tune catalog ranking so historical journal docs do not outrank code parts too easily for some query shapes.
- Consider exposing a code-only or docs-only search mode as a first-class catalog option.

## 2026-04-08T03:17:18.031061-05:00 | Evidence shelf polish for parts catalog search

- Consider adding a first-class prefer_code flag so evidence shelves can bias away from docs when the user is clearly asking for implementation anchors.
- Consider shelf summaries that adapt to intent target like structural vs verbatim vs semantic.

## 2026-04-08T07:06:17.050047-05:00 | Evidence-shelf steering and canonical-doc weighting

- Build one-call archive-to-sandbox intake for bundled examples.
- Add first-class code_only/docs_only style search modes if the current steering knobs prove too coarse during continued dogfooding.

## 2026-04-08T07:37:20.466000-05:00 | One-call archive-to-sandbox intake

- Add manifest-aware bundle summaries and likely entrypoint hints to the one-call intake response.
- Consider an optional default target-dir derivation from archive stem for even lower-friction intake.

## 2026-04-08T07:43:26.979462-05:00 | Manifest-aware intake summaries and entrypoint hints

- Harden guarded hot-reload or manifest refresh for self-generated tool stubs.
- Consider optional entrypoint confidence tuning once more bundle families are studied.

## 2026-04-08T08:00:26.445891-05:00 | Guarded extension refresh and hot-reload

- Add allowlisted sysops wrappers with explicit boundaries and no broad shell escape hatch.
- Consider extension-lane support for additional managers only if a concrete need appears.

## 2026-04-08T08:05:01.910067-05:00 | Initial allowlisted sysops wrappers

- Expand the sysops allowlist only through narrowly scoped read-only or explicitly gated wrappers.
- Consider additional wrappers like repo-root discovery or branch/ref summaries only if they materially help bounded workflows.

## 2026-04-08T08:30:17.343658-05:00 | Expanded allowlisted git wrappers

- Continue expanding sysops only through narrow read-only or explicitly gated wrappers.
- Sidecar overwrite diff reporting remains the next non-sysops pending tranche.

## 2026-04-09T10:39:03.6538820-05:00 | Monitor helper grounding, memory, and echo safety

- Formalize model policy defaults now that the loop slot and monitor-helper model lanes are both proven live.
- Build the first bounded bootstrap runner on top of the loop slot for scaffold-first local tool use.
