#!/usr/bin/env python3
"""
Pull WC2026 match data from ESPN's public scoreboard and write results.csv
in the format scoring.py expects.

Stdlib only. No API key required. The endpoint is unofficial but stable.

Usage
-----
    python3 fetch_results.py                       # default dates + teams CSV
    python3 fetch_results.py --output results.csv  # explicit output
    python3 fetch_results.py --dates 20260611-20260615  # narrower window

The 48 team names in this project are aligned to ESPN's spelling, so no
translation table is needed. If ESPN renames anything mid-tournament, the
script prints a warning naming the unmatched team(s); fix the CSV or add
an alias and re-run.

A team's "stage" is the deepest stage in which it appears as a competitor.
The CHAMPION stage is synthetic: it is awarded to the winner of the final
match (ESPN does not emit a CHAMPION slug).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
DEFAULT_DATES = "20260611-20260720"   # group stage start → final + a buffer

# ESPN season.slug  ->  scoring.py stage code
STAGE = {
    "group-stage":    "GROUP",
    "round-of-32":    "R32",
    "round-of-16":    "R16",
    "quarterfinals":  "QF",
    "semifinals":     "SF",
    "final":          "FINAL",
}
STAGE_ORDER = ["GROUP", "R32", "R16", "QF", "SF", "FINAL", "CHAMPION"]


def fetch_events(dates: str) -> list[dict]:
    url = f"{ENDPOINT}?dates={dates}"
    req = urllib.request.Request(url, headers={"User-Agent": "wc2026-sweepstake/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    return payload.get("events", [])


def is_completed(event: dict) -> bool:
    t = event.get("status", {}).get("type", {})
    return bool(t.get("completed")) or t.get("state") == "post"


def is_in_progress(event: dict) -> bool:
    """True for matches currently being played (includes halftime, ET)."""
    return event.get("status", {}).get("type", {}).get("state") == "in"


def parse_match(event: dict) -> dict | None:
    """Return a normalised match dict, or None if it isn't usable."""
    slug = event.get("season", {}).get("slug")
    stage = STAGE.get(slug)
    if stage is None:
        return None
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    if len(competitors) != 2:
        return None
    teams = []
    for c in competitors:
        name = (c.get("team") or {}).get("displayName", "").strip()
        score_raw = c.get("score", 0)
        try:
            score = int(score_raw) if score_raw not in (None, "") else 0
        except (TypeError, ValueError):
            score = 0
        teams.append({
            "name": name,
            "score": score,
            "winner": bool(c.get("winner")),
            "homeAway": c.get("homeAway", ""),
        })
    return {
        "stage": stage,
        "completed": is_completed(event),
        "in_progress": is_in_progress(event),
        "date": (event.get("date") or "")[:10],  # YYYY-MM-DD
        "teams": teams,
    }


def bump_stage(stats: dict, team: str, stage: str) -> None:
    cur = stats[team]["stage"]
    if STAGE_ORDER.index(stage) > STAGE_ORDER.index(cur):
        stats[team]["stage"] = stage


def aggregate(events: list[dict], known_teams: set[str]) -> tuple[dict, list[str]]:
    """Return (per-team stats, list of unmatched ESPN team names)."""
    stats = {t: {"gw": 0, "gd": 0, "gl": 0, "gf": 0, "ga": 0, "stage": "GROUP"}
             for t in known_teams}
    unmatched: set[str] = set()
    final_winner: str | None = None

    for ev in events:
        m = parse_match(ev)
        if m is None:
            continue
        # Include in-progress matches so the table reflects live scores;
        # the next cron pass will overwrite with the latest state, and
        # ESPN flips to completed at full-time.
        if not m["completed"] and not m["in_progress"]:
            continue
        a, b = m["teams"]
        for t in (a, b):
            if t["name"] not in stats:
                unmatched.add(t["name"])

        if a["name"] not in stats or b["name"] not in stats:
            continue

        if m["stage"] == "GROUP":
            stats[a["name"]]["gf"] += a["score"]
            stats[a["name"]]["ga"] += b["score"]
            stats[b["name"]]["gf"] += b["score"]
            stats[b["name"]]["ga"] += a["score"]
            if a["score"] > b["score"]:
                stats[a["name"]]["gw"] += 1
                stats[b["name"]]["gl"] += 1
            elif b["score"] > a["score"]:
                stats[b["name"]]["gw"] += 1
                stats[a["name"]]["gl"] += 1
            else:
                stats[a["name"]]["gd"] += 1
                stats[b["name"]]["gd"] += 1
        else:
            # Knockout: both teams REACHED this stage. Winners will also
            # appear in the next round's match and get bumped from there.
            bump_stage(stats, a["name"], m["stage"])
            bump_stage(stats, b["name"], m["stage"])
            if m["stage"] == "FINAL" and m["completed"]:
                if a["winner"]:
                    final_winner = a["name"]
                elif b["winner"]:
                    final_winner = b["name"]
                elif a["score"] != b["score"]:
                    final_winner = a["name"] if a["score"] > b["score"] else b["name"]

    if final_winner:
        stats[final_winner]["stage"] = "CHAMPION"

    return stats, sorted(unmatched)


def load_known_teams(path: str) -> set[str]:
    teams: set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            teams.add(row["country"].strip())
    return teams


def load_groups(path: str) -> dict[str, str]:
    """country -> group letter, used to label group-stage matches."""
    groups: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            groups[row["country"].strip()] = row.get("group", "").strip()
    return groups


def build_matches(events: list[dict], known: set[str], groups: dict[str, str]) -> list[dict]:
    """One row per fixture (both competitors known). Scores blank until played."""
    matches = []
    for ev in events:
        m = parse_match(ev)
        if m is None:
            continue
        a, b = m["teams"]
        if a["name"] not in known or b["name"] not in known:
            continue  # skip TBD / unmatched knockout placeholders
        # Order home then away when ESPN designates it; otherwise keep as-is.
        if b["homeAway"] == "home" and a["homeAway"] != "home":
            a, b = b, a
        group = groups.get(a["name"], "") if m["stage"] == "GROUP" else ""
        # Populate scores for both completed and in-progress matches; the
        # per-team aggregates in results.csv still only count completed
        # matches, so standings don't churn between HT and FT.
        has_score = m["completed"] or m["in_progress"]
        matches.append({
            "date": m["date"],
            "stage": m["stage"],
            "group": group,
            "home": a["name"],
            "home_score": a["score"] if has_score else "",
            "away": b["name"],
            "away_score": b["score"] if has_score else "",
        })
    matches.sort(key=lambda r: (r["date"], STAGE_ORDER.index(r["stage"]), r["home"]))
    return matches


def write_matches(matches: list[dict], path: str) -> None:
    cols = ["date", "stage", "group", "home", "home_score", "away", "away_score"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(matches)


def write_results(stats: dict, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["country", "gw", "gd", "gl", "gf", "ga", "stage"])
        for team in sorted(stats):
            s = stats[team]
            w.writerow([team, s["gw"], s["gd"], s["gl"], s["gf"], s["ga"], s["stage"]])


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Fetch WC2026 results from ESPN")
    ap.add_argument("--teams", default=os.path.join(here, "wc2026_groups_fifa_ranking.csv"),
                    help="CSV listing the 48 teams (for name validation)")
    ap.add_argument("--output", default=os.path.join(here, "results.csv"),
                    help="where to write results.csv")
    ap.add_argument("--matches", default=os.path.join(here, "matches.csv"),
                    help="where to write the match-by-match matches.csv")
    ap.add_argument("--dates", default=DEFAULT_DATES, help="YYYYMMDD-YYYYMMDD range")
    args = ap.parse_args(argv)

    known = load_known_teams(args.teams)
    groups = load_groups(args.teams)

    try:
        events = fetch_events(args.dates)
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach ESPN ({e}). Existing results.csv left untouched.",
              file=sys.stderr)
        return 2

    print(f"Fetched {len(events)} events from ESPN ({args.dates}).")

    stats, unmatched = aggregate(events, known)
    if unmatched:
        print(f"WARNING: ESPN teams not in your CSV (skipped): {unmatched}", file=sys.stderr)

    played = sum(1 for v in stats.values()
                 if v["gw"] + v["gd"] + v["gl"] > 0 or v["stage"] != "GROUP")
    champion = next((t for t, s in stats.items() if s["stage"] == "CHAMPION"), None)
    write_results(stats, args.output)
    print(f"Wrote {args.output}: {played}/48 teams with played matches"
          + (f", champion: {champion}." if champion else "."))

    matches = build_matches(events, known, groups)
    played_matches = sum(1 for m in matches if m["home_score"] != "")
    write_matches(matches, args.matches)
    print(f"Wrote {args.matches}: {len(matches)} fixtures, {played_matches} played.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
