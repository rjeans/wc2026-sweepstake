# World Cup 2026 Family Sweepstake

A small, dependency-free toolkit to run a fair, fun World Cup sweepstake for a
group of people: it splits the 48 teams into balanced squads, then keeps a live
points table through the tournament.

Eight players, six teams each, all 48 nations of the 2026 World Cup allocated so
that everyone gets a comparable spread of strength — and a single league table
where the owner of the eventual champions is the strong favourite to win.

## What's in here

| File | Purpose |
|------|---------|
| `wc2026_groups_fifa_ranking.csv` | The 48 teams: group, seeding position, country, FIFA rank. The input data. |
| `sweepstake.py` | The **allocator** — deals the 48 teams into balanced squads. |
| `scoring.py` | The **scorer** — turns match results into the live league table. |
| `sim.py` | Monte Carlo that **calibrates** the champion bonus (re-run if you change scoring). |
| `sample_allocation.csv` | An example draw (from `--seed 7`). |
| `results_template.csv` | Blank results sheet (all 48 teams) to fill in as the tournament unfolds. |

**Requirements:** Python 3.10+. Standard library only — nothing to install.

## Quick start

```bash
# 1. Do the draw (writes who owns which teams)
python3 sweepstake.py --seed 7 --output allocation.csv

# 2. As results come in, edit results.csv (start from the template), then:
python3 scoring.py --alloc allocation.csv --results results.csv --output standings.csv
```

Use `--seed` for a reproducible draw; drop it for a fresh random one.

## How the allocation works

All 48 teams are sorted by FIFA rank and cut into **6 tiers of 8** (tier 1 = the
8 strongest, … tier 6 = the 8 weakest). Every player gets **exactly one team
from each tier**, so everyone holds one elite side, one minnow, and four in
between. Two rules are enforced:

- Each player gets one team from every tier (comparable strength).
- No player holds more than one team from the same group.

Two modes:

- **`balanced`** (default) — deals teams to even out each player's total rank as
  much as possible. Tightest balance (rank-sum spread ~10–13).
- **`snake`** — a classic serpentine draft. More of a live-draft feel, but the
  spread is structurally fixed at ~32, so squads are less even. Use
  `--mode snake`.

```bash
python3 sweepstake.py --mode snake --seed 7      # alternative draft style
python3 sweepstake.py --names Alice Bob Cara Dan  # custom players (count must divide 48)
```

## How the scoring works

A player's score is the sum over their six teams of group points plus a
cumulative bonus for how far each team progresses:

| Event | Points |
|-------|-------:|
| Group-stage win / draw | 3 / 1 |
| Reach the round of 32 (qualify) | 5 |
| Reach the last 16 | 10 |
| Reach the quarter-final | 18 |
| Reach the semi-final | 30 |
| Reach the final | 45 |
| **Win the World Cup** | **80** |

The table is sorted by points, then goals for, then goal difference.

### Why the champion is worth 80 — "probably certain"

Because each player owns six teams, a broad spread of decent runs can rival the
owner of the actual winner. The champion bonus is tuned so the **winner's owner
finishes top about 92% of the time** (`sim.py`, 9,000 simulated tournaments).

| Champion worth | P(winner's owner tops table) |
|---:|---:|
| 45 | ~42% |
| 60 | ~68% |
| 75 | ~89% |
| **80** | **~92%** |
| 90 | ~97% |
| 120 | ~99.9% |
| 220 | 100% (mathematically certain, worst-case proof) |

So roughly 1 tournament in 12, a sly broad portfolio can pip the winner's owner.
That's deliberate — the alternative (an airtight guarantee) forces a champion
bonus of ~220, which makes the table lopsided. The figure is model-dependent, so
treat it as "about 90%", not an exact dial.

## Running it during the tournament

1. Copy `results_template.csv` to `results.csv`.
2. After each round, update each team's row:
   - `gw,gd,gl` — group-stage wins / draws / losses
   - `gf,ga` — goals for / against (used for tiebreakers)
   - `stage` — deepest stage reached: `GROUP, R32, R16, QF, SF, FINAL, CHAMPION`
3. Re-run `scoring.py` for the latest table. Teams left at `GROUP` just score
   their group points. Country names must match the allocation exactly
   (note the cedilla in `Curaçao`).

## Tuning

All scoring constants live at the top of `scoring.py` (`GROUP_WIN`, `INCREMENT`).
If you change them, re-run `python3 sim.py` to see the new probability that the
winner's owner tops the table, and set `INCREMENT["CHAMPION"]` accordingly.

## Developing with uv (optional)

If you have [uv](https://github.com/astral-sh/uv) installed, you can run the
scripts through an isolated, version-pinned environment instead of relying on
whatever Python your system happens to ship:

```bash
uv run sweepstake.py --seed 7 --output allocation.csv
uv run scoring.py --alloc allocation.csv --results results.csv --output standings.csv
uv run sim.py
```

uv reads `pyproject.toml` and `.python-version` to pin Python 3.10 for the
project, creates a local `.venv/` on first run, and installs nothing (this
project is stdlib-only). The `python3 …` commands shown above still work
unchanged; this is just an alternative dev workflow.

## Data note

Rankings come from the live FIFA list used in June 2026 (last official update
1 April 2026; the live list shifts a few positions, e.g. Morocco 7 / Netherlands
8). It is a strength proxy, not a prediction.
