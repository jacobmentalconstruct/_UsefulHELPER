# Current Tasklist

Updated: 2026-04-09T10:39:03.6538820-05:00

## Completed

- [x] Deepen the sandbox workbench with cartridge/CAS-style ingest and archive tooling
- [x] Polish the parts-catalog evidence shelf with intent-targeted steering and canonical-doc weighting
- [x] Build one-call archive-to-sandbox intake for bundled examples
- [x] Harden one-call archive-to-sandbox intake with manifest-aware bundle summaries and likely entrypoint hints
- [x] Harden guarded hot-reload or manifest refresh for self-generated tool stubs
- [x] Add allowlisted sysops wrappers with explicit boundaries and no broad shell escape hatch
- [x] Add sidecar overwrite diff reporting and reinstall ergonomics
- [x] Add a lightweight Tkinter operator monitor over runtime events and logs
- [x] Add right-click monitor helper actions with model-backed summaries, questions, and settings
- [x] Polish the monitor helper UX after live operator feedback
- [x] Add a reusable inference loop cartridge and manager-owned loop slot
- [x] Ground the monitor helper with structured context packets, sliding conversation memory, and prompt-echo safety

## Current

- [ ] Parked state after the monitor-helper grounding and safety tranche
  The operator helper is now materially stronger for day-to-day learning and inspection. Summaries and questions run against structured monitor-context packets instead of raw panel text alone, simple log/event questions are answered mechanically before the model is consulted, follow-up questions keep a small sliding conversation window with summarized falloff, and tiny-model prompt-echo failures now degrade to a clear “try a larger model” answer. The code path is covered and the repo is parked cleanly with verification green.

## Next Up

- [ ] Formalize model policy defaults for `0.5b`, `4b`, `7b`, and `9b` task classes
  This is the immediate next tranche. Now that inference runs through a reusable slot, we should turn model selection from README guidance into explicit worker policy for cheap, consistent local tool use.

## Future

- [ ] Build the first bounded bootstrap runner on top of the loop slot
  Use the local model as a constrained project builder for scaffolding, selected-part placement, and clean stop conditions.

- [ ] Distill the strongest reusable patterns from `.possible-tools/` into new bounded import, reference, and packaging tools
  Promote the best intake ideas into first-class tools.
