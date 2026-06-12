#!/usr/bin/env python3
"""
World Cup 2026 sweepstake scoring  -  single points table.

Scoring
-------
Group stage (per match):   win = 3, draw = 1   (max 9 per team)
Knockout progression (cumulative bonus a team keeps once it reaches a round):
    qualify / reach R32 :   5
    reach last 16       :  10
    reach quarter-final :  18
    reach semi-final    :  30
    reach final         :  45
    WIN THE CUP         :  80     <- calibrated to ~90% (see below)

A person's score = sum over their 6 teams of (group points + progression bonus).
Table is sorted by points, then goal difference, then goals for.

Calibration: "probably certain", not certain
---------------------------------------------
The title is worth 80 (i.e. +35 over reaching the final). A Monte Carlo of
9,000 simulated tournaments (FIFA-points match model, random knockout draw,
balanced allocation) puts the WINNER'S OWNER top of the table about 92% of the
time at this value. The trade-off curve:

    champion worth  45 -> 43% | 60 -> 69% | 75 -> 90% | 80 -> ~92%
                    90 -> 97% | 120 -> 99.9% | 220 -> 100% (worst-case proof)

So in roughly 1 tournament in 12, a "broad" portfolio (several deep runs spread
across someone's six teams) can pip the winner's owner. That is by design: you
asked for ~90%, not the lopsided certainty that 220 would force. The figure is
model-dependent (a different match model shifts the 90% point a few units);
the constant is at the top of the file if you want to dial it.

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
import sys

GROUP_WIN, GROUP_DRAW, GROUP_MATCHES = 3, 1, 3

STAGE_ORDER = ["GROUP", "R32", "R16", "QF", "SF", "FINAL", "CHAMPION"]
INCREMENT = {
    "GROUP": 0, "R32": 5, "R16": 5, "QF": 8, "SF": 12, "FINAL": 15, "CHAMPION": 35,
}
LOSERS_AT = {"FINAL": 1, "SF": 2, "QF": 4, "R16": 8, "R32": 16}

STAGE_ALIASES = {
    "GROUPS": "GROUP", "GROUP": "GROUP", "OUT": "GROUP", "": "GROUP",
    "RO32": "R32", "R32": "R32", "ROUND OF 32": "R32",
    "RO16": "R16", "R16": "R16", "ROUND OF 16": "R16", "LAST 16": "R16",
    "QF": "QF", "QUARTER": "QF", "QUARTERFINAL": "QF", "QUARTER-FINAL": "QF",
    "SF": "SF", "SEMI": "SF", "SEMIFINAL": "SF", "SEMI-FINAL": "SF",
    "F": "FINAL", "FINAL": "FINAL", "RUNNER-UP": "FINAL", "RUNNERUP": "FINAL",
    "W": "CHAMPION", "WIN": "CHAMPION", "WINNER": "CHAMPION", "CHAMPION": "CHAMPION",
    "CHAMPIONS": "CHAMPION",
}

# Simulated P(winner's owner tops the table) at this champion value (~92%).
CALIBRATED_PROBABILITY = 0.92


def cumulative(stage: str) -> int:
    total = 0
    for s in STAGE_ORDER:
        total += INCREMENT[s]
        if s == stage:
            return total
    raise ValueError(f"unknown stage {stage!r}")


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
            if STAGE_ORDER.index(r["stage"]) > STAGE_ORDER.index(deepest):
                deepest = r["stage"]
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
                  f"This is the ~{round((1-CALIBRATED_PROBABILITY)*100)}% tail "
                  "the 90%-calibration accepts.")
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
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    champ, rival = worst_case()
    print(f"Champion worth {champ}; calibrated to ~{round(CALIBRATED_PROBABILITY*100)}% "
          "chance the winner's owner finishes top (simulated).")
    print(f"(Worst-case pathological draw could reach {rival}; making it certain would "
          "need champion ~220. You chose ~90%.)\n")

    owners, teams_of = load_alloc(args.alloc)
    results = load_results(args.results)
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
