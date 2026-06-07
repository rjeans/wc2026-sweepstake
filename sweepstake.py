#!/usr/bin/env python3
"""
World Cup 2026 sweepstake allocator.

Splits the 48 World Cup teams among a group of people so that:
  * everyone gets the same number of teams (48 / n_people),
  * the squads are comparable in strength,
  * no person holds more than one team from the same group.

Strength proxy: FIFA world ranking (lower number = stronger team).

Method (both modes share the tier idea)
---------------------------------------
Sort the 48 teams by FIFA rank and cut into N equal strength tiers
(N = teams per person; here 6 tiers of 8). Every person receives exactly ONE
team from each tier. That alone guarantees the fairness that matters most in a
sweepstake: everyone holds exactly one top-8 side, one minnow, and so on, so
everyone has a comparable shot at "holding the winner".

Two ways to fill the squads:

  balanced (default) - after the one-per-tier rule, teams are dealt to even out
      each person's total rank as much as possible (the person with the
      strongest squad so far absorbs the weakest team in the next tier).
      Tightest strength balance. The draw still randomises who ends up with
      which finished squad. Recommended when "comparable lists" is the priority.

  snake - a classic serpentine draft (1..k, k..1, ...). More of a live-draft
      feel, but note the total-rank spread is structurally fixed by the tier
      shape, so it is wider than 'balanced'. The draw decides team-to-person
      directly, pick by pick.

The "<=1 team per group per person" rule is enforced as each tier is dealt; a
person is simply never given a team from a group they already hold (with a
bipartite-matching fallback so a valid deal is always found).
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    group: str
    group_rank: int
    country: str
    fifa_rank: int


DEFAULT_NAMES = ["Richard", "Nichola", "Emily", "Henry", "Sophie", "Tega", "Pete", "Ella"]


def load_teams(path: str) -> list[Team]:
    teams: list[Team] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            teams.append(
                Team(
                    group=row["group"].strip(),
                    group_rank=int(row["group_rank"]),
                    country=row["country"].strip(),
                    fifa_rank=int(row["fifa_rank"]),
                )
            )
    return teams


def make_tiers(teams: list[Team], n_tiers: int) -> list[list[Team]]:
    """Split teams (strongest first) into n_tiers equal strength bands."""
    ordered = sorted(teams, key=lambda t: t.fifa_rank)
    size = len(ordered) // n_tiers
    return [ordered[i * size : (i + 1) * size] for i in range(n_tiers)]


def _legal_match(people, tier_teams, held_groups, prefer):
    """
    Give each person one team from this tier, respecting the group rule.

    `prefer(person, sorted_teams)` yields candidate teams in the order that
    person would like them. Greedy in `people` order; bipartite-matching
    fallback guarantees a valid deal if one exists. Returns {person: Team}|None.
    """
    teams = sorted(tier_teams, key=lambda t: t.fifa_rank)
    taken, used = {}, set()
    for p in people:
        for t in prefer(p, teams):
            if t.country in used or t.group in held_groups[p]:
                continue
            taken[p], _ = t, used.add(t.country)
            break
    if len(taken) == len(people):
        return taken

    legal = {p: [t for t in teams if t.group not in held_groups[p]] for p in people}
    match: dict[str, str] = {}

    def augment(p, seen):
        for t in legal[p]:
            if t.country in seen:
                continue
            seen.add(t.country)
            if t.country not in match or augment(match[t.country], seen):
                match[t.country] = p
                return True
        return False

    for p in people:
        augment(p, set())
    if len(match) != len(people):
        return None
    by_country = {t.country: t for t in teams}
    return {p: by_country[c] for c, p in match.items()}


def allocate_snake(teams, names, n_tiers, rng):
    tiers = make_tiers(teams, n_tiers)
    order = names[:]
    rng.shuffle(order)
    squads = {p: [] for p in names}
    held = {p: set() for p in names}
    for ti, tier in enumerate(tiers):
        seq = order if ti % 2 == 0 else list(reversed(order))
        deal = _legal_match(seq, tier, held, prefer=lambda p, ts: ts)  # strongest first
        if deal is None:
            return None
        for p in seq:
            squads[p].append(deal[p])
            held[p].add(deal[p].group)
    return squads


def allocate_balanced(teams, names, n_tiers, rng):
    tiers = make_tiers(teams, n_tiers)
    squads = {p: [] for p in names}
    held = {p: set() for p in names}
    sums = {p: 0 for p in names}
    for tier in tiers:
        # lowest running-sum (strongest squad) picks first and absorbs the
        # weakest legal team; random tiebreak keeps draws varied & seedable.
        seq = sorted(names, key=lambda p: (sums[p], rng.random()))
        deal = _legal_match(
            seq, tier, held, prefer=lambda p, ts: list(reversed(ts))  # weakest first
        )
        if deal is None:
            return None
        for p in seq:
            t = deal[p]
            squads[p].append(t)
            held[p].add(t.group)
            sums[p] += t.fifa_rank
    return squads


def rank_sum(squad) -> int:
    return sum(t.fifa_rank for t in squad)


def spread(squads) -> int:
    s = [rank_sum(v) for v in squads.values()]
    return max(s) - min(s)


def validate(squads, n_teams, per_person):
    flat = [t.country for v in squads.values() for t in v]
    assert len(flat) == n_teams == len(set(flat)), "team count / duplicate error"
    for p, v in squads.items():
        assert len(v) == per_person, f"{p} has {len(v)} teams"
        g = [t.group for t in v]
        assert len(g) == len(set(g)), f"{p} holds two teams from one group"


def build(teams, names, mode="balanced", seed=None, candidates=None):
    if len(teams) % len(names) != 0:
        raise ValueError(f"{len(teams)} teams cannot split evenly among {len(names)}")
    per_person = len(teams) // len(names)
    fn = allocate_balanced if mode == "balanced" else allocate_snake
    if candidates is None:
        candidates = 3000 if mode == "balanced" else 1  # snake spread is fixed

    master = random.Random(seed)
    best, best_score, valid, tries = None, None, 0, 0
    cap = candidates * 300 + 500
    while valid < candidates and tries < cap:
        tries += 1
        squads = fn(teams, names, per_person, random.Random(master.random()))
        if squads is None:
            continue
        valid += 1
        sc = spread(squads)
        if best_score is None or sc < best_score:
            best, best_score = squads, sc
    if best is None:
        raise RuntimeError("No valid allocation found")
    validate(best, len(teams), per_person)
    return best, best_score, per_person


def tier_of(teams, n_tiers):
    m = {}
    for i, tier in enumerate(make_tiers(teams, n_tiers), 1):
        for t in tier:
            m[t.country] = i
    return m


def report(squads, teams, per_person, mode):
    tiers = tier_of(teams, per_person)
    print("=" * 66)
    print(f"WORLD CUP 2026 SWEEPSTAKE  -  {mode} mode")
    print("=" * 66)
    for p in sorted(squads, key=lambda p: rank_sum(squads[p])):
        sq = sorted(squads[p], key=lambda t: t.fifa_rank)
        print(f"\n{p}  (rank-sum {rank_sum(sq)}, best #{sq[0].fifa_rank})")
        for t in sq:
            print(f"    #{t.fifa_rank:<3} {t.country:<22} Grp {t.group}  tier {tiers[t.country]}")
    s = [rank_sum(v) for v in squads.values()]
    print("\n" + "-" * 66)
    print(f"Strength balance: rank-sums {min(s)}-{max(s)} (spread {max(s)-min(s)}; "
          f"lower = more equal)")
    print("Valid: 48 teams dealt once, one team per tier each, no group clashes.")
    print("-" * 66)


def write_csv(squads, teams, per_person, path):
    tiers = tier_of(teams, per_person)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["person", "country", "group", "fifa_rank", "tier"])
        for p in sorted(squads):
            for t in sorted(squads[p], key=lambda x: x.fifa_rank):
                w.writerow([p, t.country, t.group, t.fifa_rank, tiers[t.country]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="World Cup 2026 sweepstake allocator")
    ap.add_argument("--input", default="wc2026_groups_fifa_ranking.csv",
                    help="CSV with columns group,group_rank,country,fifa_rank")
    ap.add_argument("--names", nargs="+", default=DEFAULT_NAMES)
    ap.add_argument("--mode", choices=["balanced", "snake"], default="balanced")
    ap.add_argument("--seed", type=int, default=None, help="reproducible draw")
    ap.add_argument("--candidates", type=int, default=None,
                    help="search depth for balanced mode (default 3000)")
    ap.add_argument("--output", default=None, help="optional result CSV path")
    args = ap.parse_args(argv)

    teams = load_teams(args.input)
    squads, _, per = build(teams, args.names, args.mode, args.seed, args.candidates)
    report(squads, teams, per, args.mode)
    if args.output:
        write_csv(squads, teams, per, args.output)
        print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
