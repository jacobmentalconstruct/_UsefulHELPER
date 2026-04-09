# TODO

This is the human-readable TODO mirror for UsefulHELPER.

Canonical live state still belongs to:

- `_docs/_AppJOURNAL/CURRENT_TASKLIST.md`
- `_docs/_AppJOURNAL/BACKLOG.md`

## Next

- Formalize model policy defaults for `0.5b`, `4b`, `7b`, and `9b` task classes now that inference runs through a reusable loop slot.
- Build the first bounded bootstrap runner on top of the loop slot so a local model can scaffold projects, place selected parts, and stop cleanly.
- Distill the strongest reusable patterns from `.possible-tools/` into new bounded import, reference, and packaging tools.

## Notes

- `ollama.chat_json` is implemented and no longer belongs in the active TODO set.
- `fs.search_text`, `python.run_unittest`, `python.run_compileall`, and `ollama.list_models` are now live and verified.
- `archive.inspect_zip` and `archive.extract_zip` are now live and verified.
- `intake.zip_to_sandbox` is now live and verified.
- `intake.zip_to_sandbox` now returns manifest-aware bundle summaries and likely entrypoint hints.
- `worker.refresh_extension_tools` is now live and verified.
- the allowlisted Git sysops tranche is complete: `sysops.git_status`, `sysops.git_diff_summary`, `sysops.git_repo_summary`, and `sysops.git_recent_commits`
- the sidecar reinstall tranche is complete: `sidecar.export_bundle` now supports managed diff preview through `dry_run=true` plus guarded overwrite and reinstall semantics for recognized sidecar targets
- the operator monitor tranche is complete: `run_monitor.bat` and `python -m src.app --ui monitor` now expose a grouped Tkinter view over runtime events, recent tool lanes, inference history, and the app-log tail
- the monitor helper tranche is complete: right-click `Summarize`, `Ask About`, and `Settings` actions now use local-model helper calls plus persisted per-action model/instruction settings
- the monitor helper polish tranche is complete: settings now use refreshable Ollama-model dropdowns, helper modals open near the cursor, footer buttons stay visible, and empty model replies fall back to context-aware answers
- the monitor helper grounding tranche is complete: summaries and questions now run against structured monitor-context packets, simple log/event questions use mechanical-first answers, follow-ups keep a small sliding conversation window, and prompt-echo failures now suggest trying a larger model
- the parts shelf is live: `parts.catalog_build`, `parts.catalog_search`, `parts.catalog_get`, and `parts.export_selection`
- the sandbox tool set is live: `sandbox.init`, `sandbox.ingest_workspace`, `sandbox.read_head`, `sandbox.search_head`, `sandbox.stage_diff`, `sandbox.export_head`, `sandbox.history_for_file`, and `sandbox.query_symbols`
- Historical completed phases are summarized in `_docs/dev_log.md`.

- the reusable inference loop cartridge tranche is complete: `inference.describe_loops`, `ollama.chat_text`, the `ollama.single_turn` default cartridge, and the manager-owned loop slot are now live and verified
