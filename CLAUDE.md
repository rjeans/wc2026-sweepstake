# CLAUDE.md

Guidance for Claude Code working in this repo. Read `README.md` for the
human-facing overview; this file is the working brief.

## What this project is

A dependency-free Python toolkit for a family World Cup 2026 sweepstake: deal
48 teams into 8 balanced six-team squads, then keep a live points table through
the tournament. Two scripts plus a calibration simulation.

## Commands

```bash
# Do a draw (reproducible with --seed)
python3 sweepstake.py --seed 7 --output allocation.csv

# Score the table from results (during the tournament)
python3 scoring.py --alloc allocation.csv --results results.csv --output standings.csv

# Re-calibrate the champion bonus after ANY change to scoring constants
python3 sim.py
```

There is no build step and no test suite. The scripts self-validate at runtime
(`sweepstake.py` asserts the allocation is legal; `scoring.py` prints the
calibration note and flags upsets).

## Conventions

- **Python 3.10+, standard library only.** Do not add third-party dependencies
  (no numpy/pandas) — keeping it pip-free is a goal.
- Each script is standalone and runnable via `python3 <script>.py`.
- All randomness is seedable; preserve `--seed` reproducibility.
- Keep CLI flags backward-compatible; people have commands in their notes.

## Invariants — do not break these

Allocation (`sweepstake.py`):
- 48 teams / N players must divide evenly; tiers = teams-per-player (here 6).
- Every player gets **exactly one team per strength tier**.
- **No player holds more than one team from the same group.** Enforced per tier
  with a bipartite-matching fallback. Any new allocation logic must keep this.

Scoring (`scoring.py`):
- Progression bonuses are **cumulative** (a team keeps points for every round it
  clears). `STAGE_ORDER` and `INCREMENT` define this.
- The table sorts by **points, then goals for, then goal difference**.
- The champion bonus is **calibrated, not arbitrary**. The progression ladder
  now **doubles** each round (cumulative 5/10/20/40/80/160); the cup is 160
  (`INCREMENT["CHAMPION"] = 80`), giving ~99.7% chance the winner's owner tops
  the table. **If you touch any scoring constant, you MUST re-run `sim.py` and
  reset the relevant `INCREMENT` values to match the desired probability**, then
  update `CALIBRATED_PROBABILITY` and the docstring/table to stay honest. The
  same ladder is mirrored in `predict.py` (`INCREMENT`), `sim.py` (`CUM`) and
  `src/lib/wc2026.ts` (`STAGE_BONUS`) — keep all four in sync.
- `worst_case()` reports the mathematically-certain threshold (now ~274). Don't
  delete it — it documents the trade-off between "certain" and "~99.7% certain".

## Key facts / context

- Players (default): Richard, Nichola, Emily, Henry, Sophie, Tega, Pete, Ella.
- Strength proxy is FIFA rank in the CSV; `sim.py` additionally holds FIFA
  **points** for the match model. If team data changes, update both.
- Country names are the join key across `*.csv` files and must match **exactly**,
  including the cedilla in `Curaçao`. All files are UTF-8.
- The ranking is the live June-2026 list (not the 1 April official one); a few
  positions differ. It is a proxy, not a forecast.

## The core design tension (so you don't "fix" it)

Group points spread across six teams pull against guaranteeing the winner's
owner wins. As of 24 Jun 2026 the owner chose the **progression-weighted
"doubling" ladder** (cup worth 160) for ~99.7% near-certainty, deliberately
moving away from the earlier ~90% balance (cup 80). The upset is now rare by
design. If asked to rebalance again, explain the consequence (re-calibration
across the four mirrored constant sets) rather than silently changing it.

## Typical tasks you may be asked to do

- Update `results.csv` and regenerate the standings during the tournament.
- Re-tune the champion bonus to a different target probability (use `sim.py`).
- Add features (e.g. per-match knockout points, a 3rd-place playoff bump). These
  change the calibration — always re-run `sim.py` afterwards.
- Improve the match model in `sim.py` (e.g. use the official 2026 bracket instead
  of a random knockout draw); note this shifts the calibrated bonus.

## Recaps

Daily recaps live in `src/content/recaps/<YYYY-MM-DD>.md` (frontmatter:
`title`, `pubDate`, optional `summary`). They are hand-authored — there is no
generator. House style: short paragraphs, **bold** the actors, frame matches by
owner ("Tega's Germany beat Emily's Ivory Coast").

**No violent or war metaphors.** Do not describe matches or the sweepstake with
imagery of war, death, or violence (e.g. "bloodbath", "war", "battle",
"massacre", "slaughter", "carnage", "scalp", "cage match", "grudge match").
Keep it a friendly family game: prefer "contest", "tie", "clash of owners",
"a big win", "an all-their-own tie". Standard football result-words that merely
denote a lopsided score ("rout", "demolished") and the literal term "penalty
shootout" are fine. **Before committing any recap — new or edited — review the
whole text for war/violent metaphors and remove them.**

**Every recap must include an `## Odds watch` section** summarising the `/odds`
market: the favourite and their decimal price, the chasing pack, the biggest
mover(s), and any table-vs-market divergence (a team can climb the points table
yet drift in the odds, because the odds price each player's *ceiling*, not their
current points). Pull the numbers from `src/data/predictions.json` (or run
`python3 predict.py`); compare against the snapshot in `predictions_history/`.
Flag that mid-tier *title* odds are noisy until the official knockout bracket
replaces the random draw.
