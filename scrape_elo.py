#!/usr/bin/env python3
"""
Fetch current World Football Elo Ratings from eloratings.net and write a CSV
that sim.py / predict.py read at startup.

Source: https://www.eloratings.net/World.tsv  (tab-separated, ISO-2 in col 3,
Elo rating in col 4). Ratings update daily.

Usage:
    python3 scrape_elo.py                      # writes src/data/teams_elo.csv
    python3 scrape_elo.py --output other.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
import urllib.error
import urllib.request

URL = "https://www.eloratings.net/World.tsv"

# Map our country names to eloratings.net's ISO-2 codes.
# Notable non-ISO: home nations use EN/SQ/WA/NI; Türkiye is TR.
ISO = {
    "Mexico": "MX", "South Africa": "ZA", "South Korea": "KR", "Czechia": "CZ",
    "Canada": "CA", "Bosnia-Herzegovina": "BA", "Qatar": "QA", "Switzerland": "CH",
    "Brazil": "BR", "Morocco": "MA", "Haiti": "HT", "Scotland": "SQ",
    "United States": "US", "Paraguay": "PY", "Australia": "AU", "Türkiye": "TR",
    "Germany": "DE", "Curaçao": "CW", "Ivory Coast": "CI", "Ecuador": "EC",
    "Netherlands": "NL", "Japan": "JP", "Sweden": "SE", "Tunisia": "TN",
    "Belgium": "BE", "Egypt": "EG", "Iran": "IR", "New Zealand": "NZ",
    "Spain": "ES", "Cape Verde": "CV", "Saudi Arabia": "SA", "Uruguay": "UY",
    "France": "FR", "Senegal": "SN", "Iraq": "IQ", "Norway": "NO",
    "Argentina": "AR", "Algeria": "DZ", "Austria": "AT", "Jordan": "JO",
    "Portugal": "PT", "Congo DR": "CD", "Uzbekistan": "UZ", "Colombia": "CO",
    "England": "EN", "Croatia": "HR", "Ghana": "GH", "Panama": "PA",
}


def fetch_tsv() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "wc2026-sweepstake/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse(tsv: str) -> dict[str, int]:
    """ISO-2 -> Elo rating."""
    out: dict[str, int] = {}
    for line in tsv.splitlines():
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        try:
            out[cols[2]] = int(cols[3])
        except ValueError:
            continue
    return out


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Fetch current Elo ratings")
    ap.add_argument("--output", default=os.path.join(here, "src/data/teams_elo.csv"))
    args = ap.parse_args(argv)

    try:
        tsv = fetch_tsv()
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach eloratings.net ({e}).", file=sys.stderr)
        return 2

    elo_by_iso = parse(tsv)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    missing = []
    rows = []
    for country, iso in sorted(ISO.items()):
        elo = elo_by_iso.get(iso)
        if elo is None:
            missing.append((country, iso))
            continue
        rows.append({"country": country, "iso": iso, "elo": elo, "fetched_at": fetched_at})

    if missing:
        for c, iso in missing:
            print(f"WARNING: no Elo for {c} (ISO={iso})", file=sys.stderr)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["country", "iso", "elo", "fetched_at"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {args.output}: {len(rows)}/48 teams, fetched at {fetched_at}")
    if missing:
        print(f"Missing: {[c for c, _ in missing]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
