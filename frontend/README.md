# MarginPilot — judge-facing frontend

The web presentation layer. It renders decisions; it does not make them.

```
Next.js / React / TypeScript        frontend/
        ↓ HTTP JSON
read-only FastAPI adapter           api/
        ↓ Python imports
the MarginPilot engine              src/, demo/
```

## Run it

Two processes, from the repository root:

```bash
make api      # http://127.0.0.1:8000  — the JSON adapter over the engine
make web      # http://localhost:3000  — this application
```

Or without make:

```bash
python -m api
cd frontend && npm install && npm run dev
```

The frontend reads `NEXT_PUBLIC_API_BASE` and falls back to
`http://127.0.0.1:8000`. When the engine is not running, every screen says so
and offers a retry — no screen substitutes a plausible number for a missing one.

## What is here

| Screen | Answers |
|---|---|
| `/` Overview | Should this merchant promote, what does it earn, and why |
| `/experiment` | What was tested, what came back, and what it bought |
| `/trust` | What the system refuses to do, run live, plus the reproducibility pins |
| `/audit` | The append-only decision record and whether it still verifies |

`?s=A`, `?s=B`, `?s=C` select the merchant, and the selection follows you across
screens.

## The rule this codebase holds to

**No economics in TypeScript.** `src/lib/format.ts` turns numbers into strings
and does nothing else. Every rupee figure, every gate verdict, every interval
and every decision arrives from the Python engine over HTTP. If a screen needs a
quantity the engine does not produce, the fix is an engine change — not a helper
here.

## Checks

```bash
npx tsc --noEmit   # types
npm run lint       # eslint
npm run build      # production build
```
