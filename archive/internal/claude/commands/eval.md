---
description: Run the test suite, verify the audit hash chain, and print world-corpus stats
---

Run MarginPilot's verification pass and report the results. Do not modify any files.

**Never read, print, or summarise anything under `worlds/holdout/`.** The holdout is
sealed until `make eval --final-eval` (CLAUDE.md invariant 4). Dev worlds only.

1. **Test suite** — run `make test`. It takes roughly 15 minutes; run it in the
   background and wait rather than reducing scope. Report the pass/fail count, and for
   any failure quote the assertion verbatim rather than paraphrasing it.

2. **Audit hash chain** — verify the append-only log has not been tampered with:

   ```bash
   python -c "
   from src.audit.log import AuditLog
   log = AuditLog('data/audit.db')
   print(f'entries={len(log)} experiments={len(log.experiments())} chain_intact={log.verify()}')
   "
   ```

   `chain_intact=False` means a row was edited or removed after the fact. That is a
   serious finding, not a warning — report it prominently and stop rather than
   continuing to the next step.

3. **World corpus stats** — dev worlds only:

   ```bash
   python -c "
   import numpy as np
   from pathlib import Path
   from src.world.persistence import load_world
   paths = sorted(Path('worlds/dev').glob('*.world.json'))
   print(f'dev worlds: {len(paths)}')
   n = [len(load_world(p).customers) for p in paths[:20]]
   print(f'customers/world (first 20): p50={np.median(n):,.0f} min={min(n):,} max={max(n):,}')
   "
   ```

   If `worlds/dev/` is empty, say so and suggest `make worlds` — do not generate the
   corpus yourself, since that overwrites the worlds the recorded results came from.

Report each of the three as pass/fail with its numbers. If anything fails, state which
and quote the output; do not summarise a failure as "mostly working".
