#!/usr/bin/env python3
"""
World Cup 2026 sweepstake scoring  -  single points table.

Scoring
-------
Group stage (per match):   win = 3, draw = 1   (max 9 per team)
Knockout progression (cumulative bonus a team keeps once it reaches a round).
This is the "doubling" ladder - each round is worth ~as much as the whole run
up to it, so deep runs dominate group points:
    qualify / reach R32 :    5
    reach last 16       :   10
    reach quarter-final :   20
    reach semi-final    :   40
    reach final         :   80
    WIN THE CUP         :  160     <- calibrated to ~99.7% (see below)

A person's score = sum over their 6 teams of (group points + progression bonus).
Table is sorted by points, then goal difference, then goals for.

Calibration: progression-weighted, near-certain
-----------------------------------------------
The ladder doubles each round, so the title is decisive: the cup is worth 160.
A Monte Carlo of 9,000 simulated tournaments (Elo / FIFA-points match model,
random knockout draw, balanced allocation) puts the WINNER'S OWNER top of the
table about 99.7% of the time at this value. The trade-off curve under this
ladder:

    champion worth  80 -> 50% | 120 -> 92% | 160 -> ~99.7% | 200+ -> 100%

So only about 1 tournament in ~300 lets a "broad" portfolio (several deep runs
spread across someone's six teams) pip the winner's owner. This is deliberate:
the owner chose progression-weighted near-certainty over the earlier ~90%
balance (which had the cup at 80). The figure is model-dependent; the constants
are at the top of the file if you want to dial it.

Usage
-----
    python3 scoring.py --alloc sample_allocation.csv --results results.csv
    python3 scoring.py --alloc sample_allocation.csv --results results.csv --output standings.csv

results.csv columns:  country,gw,gd,gl,gf,ga,stage
    stage in {GROUP,R32,R16,QF,SF,FINAL,CHAMPION}; teams omitted = group exit.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

GROUP_WIN, GROUP_DRAW, GROUP_MATCHES = 3, 1, 3

STAGE_ORDER = ["GROUP", "R32", "R16", "QF", "SF", "FINAL", "CHAMPION"]
INCREMENT = {
    "GROUP": 0, "R32": 5, "R16": 5, "QF": 10, "SF": 20, "FINAL": 40, "CHAMPION": 80,
}
# Winning the third-place play-off is a branch off the semi-final: the winner
# keeps SF depth but scores cumulative(SF) + THIRD_BONUS. The loser (4th) stays
# at SF. It is NOT a step in STAGE_ORDER (nothing advances "through" it).
THIRD_BONUS = 20
# Of the two beaten semi-finalists, one wins the play-off (THIRD), one stays SF.
LOSERS_AT = {"FINAL": 1, "THIRD": 1, "SF": 1, "QF": 4, "R16": 8, "R32": 16}

STAGE_ALIASES = {
    "GROUPS": "GROUP", "GROUP": "GROUP", "OUT": "GROUP", "": "GROUP",
    "RO32": "R32", "R32": "R32", "ROUND OF 32": "R32",
    "RO16": "R16", "R16": "R16", "ROUND OF 16": "R16", "LAST 16": "R16",
    "QF": "QF", "QUARTER": "QF", "QUARTERFINAL": "QF", "QUARTER-FINAL": "QF",
    "SF": "SF", "SEMI": "SF", "SEMIFINAL": "SF", "SEMI-FINAL": "SF",
    "F": "FINAL", "FINAL": "FINAL", "RUNNER-UP": "FINAL", "RUNNERUP": "FINAL",
    "W": "CHAMPION", "WIN": "CHAMPION", "WINNER": "CHAMPION", "CHAMPION": "CHAMPION",
    "CHAMPIONS": "CHAMPION",
    "3P": "THIRD", "3RD": "THIRD", "THIRD": "THIRD", "THIRD PLACE": "THIRD",
    "THIRD-PLACE": "THIRD", "3RD PLACE": "THIRD", "3RD-PLACE": "THIRD",
}

# Simulated P(winner's owner tops the table) at this champion value.
# The third-place play-off bonus (THIRD = SF + 20) lets a rival's beaten
# semi-finalist bank a little more, nudging this down from ~99.7% to ~99.2%
# with the champion held at 160 (re-run sim.py after any scoring change).
CALIBRATED_PROBABILITY = 0.992


def cumulative(stage: str) -> int:
    if stage == "THIRD":  # branch off the semi-final, not a linear step
        return cumulative("SF") + THIRD_BONUS
    total = 0
    for s in STAGE_ORDER:
        total += INCREMENT[s]
        if s == stage:
            return total
    raise ValueError(f"unknown stage {stage!r}")


def rank(stage: str) -> int:
    """Depth rank for 'how far did they get'. THIRD is a semi-final exit, so it
    ranks alongside SF; only its points differ."""
    return STAGE_ORDER.index("SF" if stage == "THIRD" else stage)


def norm_stage(s: str) -> str:
    key = (s or "").strip().upper()
    if key not in STAGE_ALIASES:
        raise ValueError(f"unknown stage {s!r}")
    return STAGE_ALIASES[key]


def worst_case():
    """The pathological draw: champion floor vs richest possible rival total."""
    max_group_per_team = GROUP_MATCHES * GROUP_WIN
    pool = []
    for stage, n in LOSERS_AT.items():
        pool += [cumulative(stage)] * n
    pool.sort(reverse=True)
    rival = sum(pool[:6]) + 6 * max_group_per_team
    return cumulative("CHAMPION"), rival


def load_alloc(path):
    owners, teams_of = {}, {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c, p = row["country"].strip(), row["person"].strip()
            owners[c] = p
            teams_of.setdefault(p, []).append(c)
    return owners, teams_of


def load_results(path):
    res = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c = row["country"].strip()
            res[c] = {
                "gw": int(row.get("gw") or 0), "gd": int(row.get("gd") or 0),
                "gl": int(row.get("gl") or 0), "gf": int(row.get("gf") or 0),
                "ga": int(row.get("ga") or 0), "stage": norm_stage(row.get("stage")),
            }
    return res


def load_ko_rounds(path):
    """Deepest knockout round each team appears in, from the bracket fixtures.

    A team that reaches a round (including qualifying for the R32) banks that
    round's progression bonus immediately - the published bracket tells us this
    before the per-team results feed marks the stage. Returns {country: stage}.
    """
    rounds = {}
    if not path or not os.path.exists(path):
        return rounds

    def credit(c, st):
        # Higher points wins ties on equal depth (THIRD outranks SF on points).
        if c and (rank(st), cumulative(st)) > (
            rank(rounds.get(c, "GROUP")), cumulative(rounds.get(c, "GROUP"))
        ):
            rounds[c] = st

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            st = norm_stage(row.get("stage"))
            if st == "GROUP":
                continue
            if st == "THIRD":
                # Only the play-off WINNER banks THIRD; nobody advances from it.
                # Live leader counts provisionally, matching the odds/table.
                if (row.get("status") or "").strip() in ("post", "in"):
                    win = (row.get("winner") or "").strip()
                    if not win:
                        hs, as_ = row.get("home_score", "").strip(), row.get("away_score", "").strip()
                        if hs and as_:
                            try:
                                h, a = int(hs), int(as_)
                                win = (row.get("home", "").strip() if h > a
                                       else row.get("away", "").strip() if a > h else "")
                            except ValueError:
                                win = ""
                    if win:
                        credit(win, "THIRD")
                continue
            i = STAGE_ORDER.index(st)
            home, away = row.get("home", "").strip(), row.get("away", "").strip()
            # Both teams have reached this round (they are in the tie).
            credit(home, st)
            credit(away, st)
            # A knockout win advances the winner to the next round. We credit the
            # LEADER of a live ('in') tie provisionally too, so the table tracks
            # in-play knockout results the same way the odds do (predict.py locks
            # the live leader). A level live score has no leader, so nothing is
            # credited until someone's ahead / the match is decided.
            hs, as_ = row.get("home_score", "").strip(), row.get("away_score", "").strip()
            win = (row.get("winner") or "").strip()
            if (row.get("status") or "").strip() in ("post", "in") and i + 1 < len(STAGE_ORDER):
                if not win and hs and as_:
                    try:
                        h, a = int(hs), int(as_)
                        win = home if h > a else away if a > h else ""
                    except ValueError:
                        win = ""
                if win:
                    credit(win, STAGE_ORDER[i + 1])
    return rounds


def team_points(r):
    return r["gw"] * GROUP_WIN + r["gd"] * GROUP_DRAW + cumulative(r["stage"])


def score(owners, teams_of, results):
    rows, champion_owner = [], None
    for person, teams in teams_of.items():
        pts = gf = gd = 0
        deepest = "GROUP"
        for c in teams:
            r = results.get(c)
            if not r:
                continue
            pts += team_points(r)
            gf += r["gf"]
            gd += r["gf"] - r["ga"]
            # Deepest run by (bracket depth, then points): a third-place finish
            # (THIRD, worth 60) reads as "Third place" - deeper than a plain
            # semi-final exit (40) but shallower than reaching the final (80).
            st = r["stage"]
            if (rank(st), cumulative(st)) > (rank(deepest), cumulative(deepest)):
                deepest = st
            if r["stage"] == "CHAMPION":
                champion_owner = person
        rows.append({"person": person, "points": pts, "gf": gf, "gd": gd, "best": deepest})
    rows.sort(key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["person"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows, champion_owner


def print_table(rows, champion_owner):
    print("=" * 62)
    print("WORLD CUP 2026 SWEEPSTAKE  -  STANDINGS")
    print("=" * 62)
    print(f"{'#':>2}  {'Player':<10}{'Pts':>5}{'GF':>5}{'GD':>5}   Best run")
    print("-" * 62)
    for r in rows:
        tag = "  <- owns the WINNER" if r["person"] == champion_owner else ""
        print(f"{r['rank']:>2}  {r['person']:<10}{r['points']:>5}{r['gf']:>5}"
              f"{r['gd']:>5}   {r['best']}{tag}")
    print("-" * 62)
    if champion_owner:
        if rows[0]["person"] == champion_owner:
            print(f"{champion_owner} owns the winner and tops the table.")
        else:
            top = rows[0]["person"]
            print(f"UPSET: {top} pipped {champion_owner} (the winner's owner). "
                  f"This is the ~{(1-CALIBRATED_PROBABILITY)*100:.1f}% tail "
                  "the progression-weighted calibration accepts.")
    else:
        print("No champion decided yet - running table.")


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "person", "points", "goals_for", "goal_diff", "best_run"])
        for r in rows:
            w.writerow([r["rank"], r["person"], r["points"], r["gf"], r["gd"], r["best"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="WC2026 sweepstake scorer")
    ap.add_argument("--alloc", default="sample_allocation.csv")
    ap.add_argument("--results", required=True)
    ap.add_argument("--matches", default=None,
                    help="matches.csv; credits progression bonuses from the bracket "
                         "as teams reach each round (e.g. +5 on qualifying for the R32)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    champ, rival = worst_case()
    print(f"Champion worth {champ}; calibrated to ~{CALIBRATED_PROBABILITY*100:.1f}% "
          "chance the winner's owner finishes top (simulated).")
    print(f"(Worst-case pathological draw could reach {rival}; this progression-weighted "
          "ladder is near-certain by design, not the earlier ~90% balance.)\n")

    owners, teams_of = load_alloc(args.alloc)
    results = load_results(args.results)

    # Credit progression from the bracket: a team that has reached a round (incl.
    # qualifying for the R32) banks that round's bonus even before the results
    # feed marks its stage. Use the deeper of the two.
    ko_rounds = load_ko_rounds(args.matches)
    for c, br in ko_rounds.items():
        r = results.get(c)
        if r and (rank(br), cumulative(br)) > (rank(r["stage"]), cumulative(r["stage"])):
            r["stage"] = br

    unknown = set(results) - set(owners)
    if unknown:
        print(f"Note: results for unallocated teams ignored: {sorted(unknown)}\n")
    rows, champ_owner = score(owners, teams_of, results)
    print_table(rows, champ_owner)
    if args.output:
        write_csv(rows, args.output)
        print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
