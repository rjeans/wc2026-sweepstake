#!/usr/bin/env python3
"""
Monte Carlo calibration for the champion bonus in scoring.py.

Simulates the World Cup many times (FIFA-points match model, random knockout
draw, balanced allocation re-drawn each trial) and reports the champion-stage
value needed for the WINNER'S OWNER to finish top of the sweepstake table at a
range of probabilities. Use this to re-tune INCREMENT["CHAMPION"] in scoring.py
whenever you change the scoring constants.

    python3 sim.py [--trials 9000] [--seed 20260605]

Stdlib only. Imports sweepstake.py and the ranking CSV from the same folder.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sweepstake as sw  # noqa: E402

CSV = os.path.join(HERE, "wc2026_groups_fifa_ranking.csv")

# Strength rating used by the match model. Prefer current Elo from
# src/data/teams_elo.csv (regenerated daily by scrape_elo.py). Falls back to
# the static FIFA points snapshot below if the Elo CSV isn't present.
_ELO_PATH = os.path.join(HERE, "src/data/teams_elo.csv")

_FIFA_POINTS_FALLBACK = {
    "Mexico": 1684.13, "South Africa": 1428.38, "South Korea": 1591.63, "Czechia": 1503.04,
    "Canada": 1560.62, "Bosnia-Herzegovina": 1385.77, "Qatar": 1452.37, "Switzerland": 1650.75,
    "Brazil": 1762.66, "Morocco": 1756.94, "Haiti": 1296.61, "Scotland": 1499.92,
    "United States": 1675.70, "Paraguay": 1503.50, "Australia": 1578.66, "Türkiye": 1601.99,
    "Germany": 1731.30, "Curaçao": 1293.08, "Ivory Coast": 1532.98, "Ecuador": 1596.48,
    "Netherlands": 1751.10, "Japan": 1661.58, "Sweden": 1510.11, "Tunisia": 1479.10,
    "Belgium": 1739.55, "Egypt": 1565.56, "Iran": 1616.04, "New Zealand": 1276.66,
    "Spain": 1876.40, "Cape Verde": 1369.29, "Saudi Arabia": 1419.73, "Uruguay": 1673.07,
    "France": 1877.32, "Senegal": 1686.41, "Iraq": 1447.77, "Norway": 1555.60,
    "Argentina": 1874.81, "Algeria": 1571.03, "Austria": 1597.40, "Jordan": 1390.10,
    "Portugal": 1763.83, "Congo DR": 1479.68, "Uzbekistan": 1461.21, "Colombia": 1695.99,
    "England": 1825.97, "Croatia": 1712.24, "Ghana": 1346.88, "Panama": 1540.60,
}


def _load_points() -> tuple[dict[str, float], str]:
    """Return (ratings, source). Tries Elo CSV first, falls back to FIFA dict."""
    if os.path.exists(_ELO_PATH):
        import csv as _csv
        out: dict[str, float] = {}
        with open(_ELO_PATH, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                try:
                    out[row["country"]] = float(row["elo"])
                except (KeyError, ValueError):
                    continue
        if len(out) >= 40:  # most teams resolved
            return out, "elo"
    return dict(_FIFA_POINTS_FALLBACK), "fifa"


POINTS, RATING_SOURCE = _load_points()

# Progression cumulative used in scoring.py (champion is the knob => 0 in base).
# THIRD = SF + 20 is the third-place play-off winner (a branch off the semi).
CUM = {"GROUP": 0, "R32": 5, "R16": 10, "QF": 20, "SF": 40, "THIRD": 60, "FINAL": 80}

# Poisson goals: lam = LAMBDA0 * exp(+/- K * rating_diff).
# Same K works for both rating sources - Elo and FIFA points happen to live on
# scales that give similar match outcome distributions under this Poisson model.
# K=0.0020 was empirically validated to track the canonical Elo win-probability
# formula 1/(1+10^(d/400)) within ~1.6pp across deltas of 50-300.
LAMBDA0 = 1.30
K = 0.0020


def _poisson(lam, rng):
    target, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= target:
            return k - 1


def _play(a, b, rng, knockout=False):
    """Returns (winner_or_None, a_goals, b_goals) — goals in input order."""
    d = POINTS[a] - POINTS[b]
    ga = _poisson(LAMBDA0 * math.exp(K * d), rng)
    gb = _poisson(LAMBDA0 * math.exp(-K * d), rng)
    if ga > gb:
        return a, ga, gb
    if gb > ga:
        return b, ga, gb
    if knockout:  # penalties, tilted by strength
        we = 1.0 / (1.0 + 10.0 ** (-d / 600.0))
        return (a if rng.random() < we else b), ga, gb
    return None, ga, gb


def simulate(teams, by_group, rng):
    stage = {t.country: "GROUP" for t in teams}
    gpts, gf, ga = {}, {}, {}
    standings = {}
    for g, cs in by_group.items():
        for c in cs:
            gpts[c] = gf[c] = ga[c] = 0
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                w, x, y = _play(cs[i], cs[j], rng)
                gf[cs[i]] += x; ga[cs[i]] += y; gf[cs[j]] += y; ga[cs[j]] += x
                if w == cs[i]:
                    gpts[cs[i]] += 3
                elif w == cs[j]:
                    gpts[cs[j]] += 3
                else:
                    gpts[cs[i]] += 1; gpts[cs[j]] += 1
        standings[g] = sorted(cs, key=lambda c: (gpts[c], gf[c] - ga[c], gf[c], rng.random()),
                              reverse=True)
    qualifiers, thirds = [], []
    for ranked in standings.values():
        qualifiers += ranked[:2]
        thirds.append(ranked[2])
    thirds.sort(key=lambda c: (gpts[c], gf[c] - ga[c], gf[c], rng.random()), reverse=True)
    qualifiers += thirds[:8]
    for c in qualifiers:
        stage[c] = "R32"
    alive = qualifiers[:]
    rng.shuffle(alive)
    sf_losers = []
    for nxt in ["R16", "QF", "SF", "FINAL", "CHAMPION"]:
        winners = []
        for i in range(0, len(alive), 2):
            a, b = alive[i], alive[i + 1]
            w, _, _ = _play(a, b, rng, knockout=True)
            winners.append(w)
            if nxt == "FINAL":  # this round's losers are the beaten semi-finalists
                sf_losers.append(b if w == a else a)
        for w in winners:
            stage[w] = nxt
        alive = winners
        rng.shuffle(alive)
    # Third-place play-off: winner banks THIRD (SF + 20), loser stays SF.
    if len(sf_losers) == 2:
        w3, _, _ = _play(sf_losers[0], sf_losers[1], rng, knockout=True)
        stage[w3] = "THIRD"
    return stage, gpts, gf, ga


def champion_value_needed(teams, names, by_group, rng):
    stage, gpts, gf, ga = simulate(teams, by_group, rng)
    squads = sw.allocate_balanced(teams, names, 6, rng)
    if squads is None:
        return None
    base, GF, GD, champ_owner = {}, {}, {}, None
    for p, sq in squads.items():
        b = f = d = 0
        for t in sq:
            c = t.country
            b += gpts[c] + (CUM[stage[c]] if stage[c] != "CHAMPION" else 0)
            f += gf[c]; d += gf[c] - ga[c]
            if stage[c] == "CHAMPION":
                champ_owner = p
        base[p], GF[p], GD[p] = b, f, d
    need = 0
    for o in names:
        if o == champ_owner:
            continue
        gap = base[o] - base[champ_owner]
        owner_wins_tiebreak = (GD[champ_owner], GF[champ_owner]) > (GD[o], GF[o])
        need = max(need, gap if owner_wins_tiebreak else gap + 1)
    return max(0, need)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Calibrate the champion bonus")
    ap.add_argument("--trials", type=int, default=9000)
    ap.add_argument("--seed", type=int, default=20260605)
    args = ap.parse_args(argv)

    teams = sw.load_teams(CSV)
    names = sw.DEFAULT_NAMES
    by_group = {}
    for t in teams:
        by_group.setdefault(t.group, []).append(t.country)

    rng = random.Random(args.seed)
    needed = sorted(x for _ in range(args.trials)
                    if (x := champion_value_needed(teams, names, by_group, rng)) is not None)
    n = len(needed)

    print(f"trials={n}")
    print("Champion-stage value needed for the winner's owner to top the table:")
    for q in (0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"  {int(q*100):>2}% of tournaments -> champion >= {needed[min(n-1, int(q*n))]}")
    print("\nP(winner's owner tops table) by champion value:")
    for B in (80, 120, 160, 200, 240, 320, 440):
        print(f"  champion={B:>3}: {sum(v <= B for v in needed)/n*100:5.1f}%")
    print("\nNote: model-dependent (Poisson goals + random knockout draw); treat as approximate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
