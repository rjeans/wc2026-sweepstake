#!/usr/bin/env python3
"""
Monte Carlo predictor for the WC2026 sweepstake.

Reads real fixture state from src/data/matches.csv, locks in any match
with a final score (status "post" or "in"), and simulates everything
else with the same Poisson goals model as sim.py. After N trials it
aggregates per-player odds, expected final points, and the probability
that the actual world champion sits in each player's squad.

Stdlib only. Output: src/data/predictions.json (+ stdout summary).

Usage:
    python3 predict.py                        # default 10_000 trials
    python3 predict.py --trials 5000 --seed 7 # reproducible
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim as smod  # POINTS, LAMBDA0, K, _poisson, _play

# Must match scoring.py
GROUP_WIN, GROUP_DRAW = 3, 1
INCREMENT = {"GROUP": 0, "R32": 5, "R16": 5, "QF": 8, "SF": 12, "FINAL": 15, "CHAMPION": 35}
STAGE_ORDER = ["GROUP", "R32", "R16", "QF", "SF", "FINAL", "CHAMPION"]
CUM = {}
total = 0
for s in STAGE_ORDER:
    total += INCREMENT[s]
    CUM[s] = total


def load_teams(path: str):
    teams: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            teams.append({
                "country": r["country"].strip(),
                "group": r["group"].strip(),
                "group_rank": int(r["group_rank"]),
                "fifa_rank": int(r["fifa_rank"]),
            })
    return teams


def load_allocation(path: str) -> dict[str, str]:
    owners: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            owners[r["country"].strip()] = r["person"].strip()
    return owners


def load_real_matches(path: str):
    """Return (locked_groups, locked_kos).

    locked_groups: dict[(home, away)] -> (home_score, away_score)
    locked_kos:    dict[stage] -> list of (home, away, home_score, away_score, winner|None)

    Any match with both scores present (post or in) is treated as locked. Pre matches are skipped.
    """
    locked_groups: dict[tuple[str, str], tuple[int, int]] = {}
    locked_kos: dict[str, list[tuple]] = defaultdict(list)
    if not os.path.exists(path):
        return locked_groups, dict(locked_kos)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hs, as_ = r.get("home_score", "").strip(), r.get("away_score", "").strip()
            if not hs or not as_:
                continue
            try:
                hs_i, as_i = int(hs), int(as_)
            except ValueError:
                continue
            stage = r["stage"].strip()
            home, away = r["home"].strip(), r["away"].strip()
            if stage == "GROUP":
                locked_groups[(home, away)] = (hs_i, as_i)
            else:
                if hs_i > as_i:
                    winner = home
                elif as_i > hs_i:
                    winner = away
                else:
                    winner = None  # PK shootout - ESPN normally resolves; leave to sim if not
                locked_kos[stage].append((home, away, hs_i, as_i, winner))
    return locked_groups, dict(locked_kos)


def simulate_one(teams, by_group, locked_groups, locked_kos, rng):
    """Run one full-tournament simulation seeded with locked-in matches."""
    stage = {t["country"]: "GROUP" for t in teams}
    gpts: dict[str, int] = {}
    gf: dict[str, int] = {}
    ga: dict[str, int] = {}

    standings = {}
    for g, cs in by_group.items():
        for c in cs:
            gpts[c] = gf[c] = ga[c] = 0
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                # Did this fixture actually happen? Check both orderings.
                if (a, b) in locked_groups:
                    ag, bg = locked_groups[(a, b)]
                elif (b, a) in locked_groups:
                    bg, ag = locked_groups[(b, a)]
                else:
                    _, ag, bg = smod._play(a, b, rng)
                gf[a] += ag; ga[a] += bg
                gf[b] += bg; ga[b] += ag
                if ag > bg:
                    gpts[a] += GROUP_WIN
                elif bg > ag:
                    gpts[b] += GROUP_WIN
                else:
                    gpts[a] += GROUP_DRAW
                    gpts[b] += GROUP_DRAW
        standings[g] = sorted(
            cs,
            key=lambda c: (gpts[c], gf[c] - ga[c], gf[c], rng.random()),
            reverse=True,
        )

    qualifiers, thirds = [], []
    for ranked in standings.values():
        qualifiers += ranked[:2]
        thirds.append(ranked[2])
    thirds.sort(key=lambda c: (gpts[c], gf[c] - ga[c], gf[c], rng.random()), reverse=True)
    qualifiers += thirds[:8]
    for c in qualifiers:
        stage[c] = "R32"

    # Knockout. Until ESPN publishes the official bracket we shuffle the
    # qualifiers; once group stage ends we can replace with the real pairings.
    # When a KO match is already played in matches.csv (locked_kos) we use the
    # actual winner instead of simulating.
    ko_lookup: dict[str, dict[tuple[str, str], str | None]] = {
        s: {(h, a): w for (h, a, _, _, w) in rows} for s, rows in locked_kos.items()
    }

    def _ko_winner(stage_key: str, a: str, b: str) -> str:
        lk = ko_lookup.get(stage_key, {})
        if (a, b) in lk and lk[(a, b)] is not None:
            return lk[(a, b)]
        if (b, a) in lk and lk[(b, a)] is not None:
            return lk[(b, a)]
        w, _, _ = smod._play(a, b, rng, knockout=True)
        return w

    alive = qualifiers[:]
    rng.shuffle(alive)
    for nxt in ["R16", "QF", "SF", "FINAL", "CHAMPION"]:
        winners = []
        for i in range(0, len(alive), 2):
            winners.append(_ko_winner(nxt, alive[i], alive[i + 1]))
        for w in winners:
            stage[w] = nxt
        alive = winners
        rng.shuffle(alive)

    return stage, gpts, gf, ga


def score_player(owned, stage, gpts, gf, ga):
    pts = gf_sum = gd_sum = 0
    for c in owned:
        pts += gpts.get(c, 0) + CUM[stage.get(c, "GROUP")]
        gf_sum += gf.get(c, 0)
        gd_sum += gf.get(c, 0) - ga.get(c, 0)
    return pts, gf_sum, gd_sum


def run(trials: int, teams, by_group, allocation, locked_groups, locked_kos, rng):
    players_teams: dict[str, list[str]] = defaultdict(list)
    for country, owner in allocation.items():
        players_teams[owner].append(country)
    players = sorted(players_teams.keys())
    all_teams = [t["country"] for t in teams]

    wins = Counter()
    top3 = Counter()
    pts_sum: dict[str, float] = defaultdict(float)
    pts_max: dict[str, int] = defaultdict(lambda: 0)
    champ_owner = Counter()

    # Per-team tracking
    team_stage_counts: dict[str, Counter] = {c: Counter() for c in all_teams}
    team_pts_sum: dict[str, float] = defaultdict(float)

    for _ in range(trials):
        stage, gpts, gf, ga = simulate_one(teams, by_group, locked_groups, locked_kos, rng)
        # Per-team
        for c in all_teams:
            s = stage.get(c, "GROUP")
            team_stage_counts[c][s] += 1
            team_pts_sum[c] += gpts.get(c, 0) + CUM[s]
        # Per-player
        scores = []
        for p in players:
            pts, f, d = score_player(players_teams[p], stage, gpts, gf, ga)
            scores.append((p, pts, d, f))
            pts_sum[p] += pts
            if pts > pts_max[p]:
                pts_max[p] = pts
        # Sweepstake sort: points -> GD -> GF -> name
        scores.sort(key=lambda x: (-x[1], -x[2], -x[3], x[0]))
        wins[scores[0][0]] += 1
        for s in scores[:3]:
            top3[s[0]] += 1
        champion = next((c for c, s in stage.items() if s == "CHAMPION"), None)
        if champion:
            champ_owner[allocation.get(champion)] += 1

    # Build per-team predictions
    teams_out = []
    team_info = {t["country"]: t for t in teams}
    for c in all_teams:
        counts = team_stage_counts[c]
        # P(reach stage X) = count of trials whose deepest stage >= X
        p_reach = {}
        for i, s in enumerate(STAGE_ORDER):
            p_reach[s] = sum(counts[t] for t in STAGE_ORDER[i:]) / trials
        p_champ = p_reach["CHAMPION"]
        teams_out.append({
            "country": c,
            "owner": allocation.get(c),
            "group": team_info[c]["group"],
            "fifa_rank": team_info[c]["fifa_rank"],
            "p_qualify": p_reach["R32"],
            "p_r16": p_reach["R16"],
            "p_qf": p_reach["QF"],
            "p_sf": p_reach["SF"],
            "p_final": p_reach["FINAL"],
            "p_champion": p_champ,
            "expected_points": team_pts_sum[c] / trials,
            "odds_decimal": (1.0 / p_champ) if p_champ > 0 else None,
        })
    teams_out.sort(key=lambda x: -x["p_champion"])

    out = []
    for p in players:
        pw = wins[p] / trials
        out.append({
            "player": p,
            "p_win": pw,
            "p_top3": top3[p] / trials,
            "expected_points": pts_sum[p] / trials,
            "max_points_seen": pts_max[p],
            "p_owns_champion": champ_owner[p] / trials,
            "odds_decimal": (1.0 / pw) if pw > 0 else None,
        })
    out.sort(key=lambda x: -x["p_win"])
    return out, teams_out


def _find_prior_snapshot(history_dir: str, today_iso: str) -> dict | None:
    """Return the parsed JSON of the most recent dated snapshot file older than today, or None."""
    if not os.path.isdir(history_dir):
        return None
    candidates = []
    for name in os.listdir(history_dir):
        if not name.endswith(".json"):
            continue
        date = name[:-5]
        if date < today_iso:
            candidates.append((date, name))
    if not candidates:
        return None
    candidates.sort()
    latest = candidates[-1]
    with open(os.path.join(history_dir, latest[1]), encoding="utf-8") as f:
        return json.load(f)


def _attach_movement(predictions: list[dict], team_predictions: list[dict], prior: dict) -> None:
    """Add delta_* fields against the prior snapshot's probabilities/odds."""
    prior_p = {p["player"]: p for p in prior.get("predictions", [])}
    for p in predictions:
        old = prior_p.get(p["player"])
        if not old:
            continue
        p["delta_p_win"] = p["p_win"] - old.get("p_win", 0)
        p["delta_expected_points"] = p["expected_points"] - old.get("expected_points", 0)
        if old.get("odds_decimal") and p.get("odds_decimal"):
            p["delta_odds_decimal"] = p["odds_decimal"] - old["odds_decimal"]

    prior_t = {t["country"]: t for t in prior.get("teams", [])}
    for t in team_predictions:
        old = prior_t.get(t["country"])
        if not old:
            continue
        t["delta_p_champion"] = t["p_champion"] - old.get("p_champion", 0)
        t["delta_expected_points"] = t["expected_points"] - old.get("expected_points", 0)
        if old.get("odds_decimal") and t.get("odds_decimal"):
            t["delta_odds_decimal"] = t["odds_decimal"] - old["odds_decimal"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="WC2026 sweepstake Monte Carlo predictor")
    ap.add_argument("--trials", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--teams", default=os.path.join(HERE, "src/data/teams.csv"))
    ap.add_argument("--allocation", default=os.path.join(HERE, "src/data/allocation.csv"))
    ap.add_argument("--matches", default=os.path.join(HERE, "src/data/matches.csv"))
    ap.add_argument("--output", default=os.path.join(HERE, "src/data/predictions.json"))
    ap.add_argument("--history", default=os.path.join(HERE, "src/data/predictions_history"),
                    help="Directory for dated snapshots; movement is computed against the most recent older file here.")
    args = ap.parse_args(argv)

    teams = load_teams(args.teams)
    allocation = load_allocation(args.allocation)
    locked_groups, locked_kos = load_real_matches(args.matches)

    by_group: dict[str, list[str]] = defaultdict(list)
    for t in teams:
        by_group[t["group"]].append(t["country"])
    by_group = dict(by_group)

    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    predictions, team_predictions = run(args.trials, teams, by_group, allocation, locked_groups, locked_kos, rng)

    # Movement: compare to the most recent dated snapshot that isn't today.
    today_iso = datetime.date.today().isoformat()
    os.makedirs(args.history, exist_ok=True)
    prior_snapshot = _find_prior_snapshot(args.history, today_iso)
    if prior_snapshot:
        _attach_movement(predictions, team_predictions, prior_snapshot)

    output = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "trials": args.trials,
        "locked_group_matches": len(locked_groups),
        "locked_ko_matches": sum(len(v) for v in locked_kos.values()),
        "comparison_date": (prior_snapshot or {}).get("date"),
        "predictions": predictions,
        "teams": team_predictions,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # Daily snapshot - overwrites today's file with the latest state. When tomorrow
    # rolls around, this becomes "yesterday's file" used as the movement baseline.
    snapshot_path = os.path.join(args.history, f"{today_iso}.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": today_iso,
            "generated_at": output["generated_at"],
            "trials": args.trials,
            "predictions": [{k: v for k, v in p.items() if not k.startswith("delta_")} for p in predictions],
            "teams": [{k: v for k, v in t.items() if not k.startswith("delta_")} for t in team_predictions],
        }, f, indent=2)

    print(f"trials={args.trials}  locked_group_matches={len(locked_groups)}\n")
    print(f"  {'Player':<8} {'P(win)':>8} {'P(top3)':>8} {'E[pts]':>8} {'P(champ)':>9} {'Odds':>8}")
    print("  " + "-" * 56)
    for pr in predictions:
        odds = f"{pr['odds_decimal']:.2f}" if pr["odds_decimal"] else "  -"
        print(f"  {pr['player']:<8} {pr['p_win']:>7.1%} {pr['p_top3']:>7.1%} {pr['expected_points']:>8.1f} {pr['p_owns_champion']:>8.1%} {odds:>8}")

    print(f"\n  {'Country':<22} {'Owner':<8} {'Grp':>3} {'FIFA':>5} {'P(QF)':>7} {'P(SF)':>7} {'P(F)':>7} {'P(W)':>7} {'E[pts]':>7} {'Odds':>8}")
    print("  " + "-" * 96)
    for t in team_predictions:
        odds = f"{t['odds_decimal']:.1f}" if t["odds_decimal"] and t["odds_decimal"] < 1000 else "  -"
        print(f"  {t['country']:<22} {t['owner']:<8} {t['group']:>3} {t['fifa_rank']:>5} "
              f"{t['p_qf']:>6.1%} {t['p_sf']:>6.1%} {t['p_final']:>6.1%} {t['p_champion']:>6.1%} "
              f"{t['expected_points']:>7.1f} {odds:>8}")
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
