# bring-loop

**Your agents made building easy. This gates the part they can't do for you.**

The bring loop surfaces **one outward action per day** — the send, the
decision, the close, the ship — stages it, and measures what happened in
honest, separate streams. It never sends anything for you. That's the point:
the rep is yours; the loop just makes sure the rep gets surfaced, staged, and
counted the same way your build loop already is.

Named for the **BringItCruz! effect** — coined by Cruz Romero Morales
(TresPies / DojoGenesis), whose agent-orchestrated workspace could ship 89
commits in 18 days while a single "send the package" task quietly aged 18.8
days in the operator queue. Build strong, distribute weak, *measured*: once
the gap is a number on a dashboard instead of a feeling, you can gate it. This
repo is that gate, generalized. ("Built it, now bring it.")

## Quick start (any system)

```bash
python plugin/scripts/bring_core.py init          # scaffolds bring/ in your project
$EDITOR bring/actions.md                          # list your outward actions
python plugin/scripts/bring_core.py brief         # today's ONE action
python plugin/scripts/bring_core.py log sent --id <id>
python plugin/scripts/bring_core.py check         # parity gate for the scoreboard
```

Wire `brief` into whatever starts your day — a Claude Code hook, `.bashrc`,
an editor task. One file, Python stdlib, no network, no telemetry, nothing to
sign up for. Your files, your machine, your reps.

## Claude Code users

The `plugin/` directory is a complete Claude Code plugin: a SessionStart hook
injects today's bring into every session, a Stop hook nudges once if it went
untouched, and the `bring` skill teaches the agent the contract — **surface +
stage only** (it pulls up your draft and confirms the details; you hit send),
log on your word, and a conscious skip is a valid entry.

## The five invariants

1. One action a day — never a list.
2. Surface + stage only — the human executes.
3. A logged skip is a valid rep — declined beats expired.
4. Streams stay separate (sent / decided / closed / shipped / skipped) — no
   blended score.
5. One source per concern, two faces per surface, one parity gate — the loop
   is equally navigable by you and your agents (`actions.md` for intent,
   `ledger.jsonl` for history, generated `SCOREBOARD.md` for humans, `check`
   to keep them honest).

Full pattern spec: [SPEC.md](SPEC.md). Agent front door: [llms.txt](llms.txt).

## Status

v0.1 draft. MIT licensed (license choice re-confirmed at first public
release). Origin story, prior art, and the measured baseline live in the
TresPies operator archives; the pattern is open — the knowledge is free, bring
your own trust.
