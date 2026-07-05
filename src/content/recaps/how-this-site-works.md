---
title: "Under the bonnet: how this site runs itself"
pubDate: 2026-07-05
summary: "For the technically curious: how the sweepstake site is built (mostly by an AI, from my phone), how the table and odds update themselves every half hour, and the couple of places it's held together with tape."
---

A few people have asked how this site actually works — how the table and
the odds keep changing without anyone touching them, and how a new recap
appears each morning. So here's the honest tour. Fair warning: it's less
clever than it looks, and quite a lot of it isn't really me.

## The short version

It's a static website, a handful of small Python scripts, and a robot that
runs them every half hour. There's no server, no database, no login — nothing
that can fall over at two in the morning. It costs nothing to run, and most
days I forget it exists.

## The part I should probably confess first

I don't write most of the code. I describe what I want — in plain English,
usually from my phone — and **Claude Code** does the typing. Claude is
Anthropic's AI; Claude Code is the version of it that lives in a terminal and
can actually read the files, write new ones, run the scripts, commit to git
and deploy. So a request like "add a drill-down to the teams table," or "the
odds don't reflect that France are favourites — what's going on?", turns into
real, working changes a few minutes later.

The division of labour is roughly this: I bring the ideas, the design, the
sweepstake rules and the judgement about what's worth doing; Claude brings the
ability to actually build it, without me hand-writing components at midnight.
When something breaks — and plenty has — I describe the symptom and it goes off
and finds the cause. The good calls are mine. The semicolons are its.

(Even these recaps are drafted by the AI from the day's results, and then I
read them back and cut the bits that are wrong, or too pleased with themselves.
This one included.)

## Running it from my pocket

The whole thing lives on a **Mac mini** that sits at home doing nothing
dramatic. When I ask for a change, Claude Code makes it there — which means I
can be on a train, or in the pub, and still "push a fix" by typing a sentence.

But before anything goes near the family, I want to *see* it. That's where
**Tailscale** comes in: a private network that quietly stitches all my devices
together as if they were on the same wifi. The Mac mini runs a live
development copy of the site, and Tailscale lets me open that copy from my
phone, wherever I am — same link on a train as at my desk. So the loop is: ask
for a change, Claude Code builds it on the mini, I open the Tailscale link to
check it looks right, and *only then* does it get committed and deployed for
real.

## The site itself

Built with [Astro](https://astro.build), which takes a folder of components
and markdown and turns it into plain HTML and CSS. There is almost no
JavaScript running in your browser: the drill-downs and the Fixtures toggle are
done with CSS and native `<details>` tags. That's a slightly stubborn way to
build them, but it means the pages are fast and nothing ever spins.

## The "database"

There isn't one. The data lives in a few CSV files and one JSON file,
committed straight into the git repository:

- `allocation.csv` — who owns which teams.
- `results.csv` / `matches.csv` — the scores and fixtures.
- `standings.csv` — the league table.
- `predictions.json` — the odds.

Storing your live data as text files in a git repo is either elegant or
faintly horrifying, depending on who you ask. But it means I get a complete
history for free — every version of the table is a git commit — and I never
have to think about backups. I'll take it.

## The scripts

All Python, all standard library, nothing to install:

- `fetch_results.py` pulls the scores and fixtures from ESPN's public feed.
- `scrape_elo.py` grabs each team's current Elo rating (their strength).
- `scoring.py` turns results into the league table and applies the
  progression bonuses.
- `predict.py` runs 50,000 simulated tournaments and writes out the odds.

There's a fifth, `sim.py`, that exists only to calibrate one number (more on
that below), and the original `sweepstake.py`, which did the draw back in June
and hasn't been needed since.

## The robot

A GitHub Action wakes up every 30 minutes, runs those scripts in order,
commits any changed data back to the repo, rebuilds the site and deploys it.
Every step is deliberately dull: if ESPN is down, it shrugs and tries again in
half an hour. When I push a code change, the same pipeline runs and it's live
in a couple of minutes.

## Deployment

It's [Cloudflare Pages](https://pages.cloudflare.com). It watches the repo, and
when anything changes it builds the site and pushes it out to their network;
the domain points at that. That is the entire operations story. There is
genuinely nothing for me to keep alive.

## The honest bit — where it's held together with tape

- For about two weeks the odds were quietly wrong. The Elo scraper had failed
  once and overwritten its own data with an empty file, so everything silently
  fell back to a static ranking table. Nobody noticed until someone asked why
  France weren't favourites. It now refuses to overwrite good data with
  rubbish — the sort of guardrail you should put in on day one and, reader, I
  did not.
- Penalty shootouts broke the scoring. A 1-1 knockout that goes to spot-kicks
  looks like a draw in the data, so for a day nobody's team "advanced". Fixed
  by recording the actual winner ESPN reports.
- The champion bonus is deliberately enormous (160 points) so the sweepstake
  tracks who actually *wins* the tournament, not who hoarded the most
  group-stage draws. That number isn't a guess — `sim.py` runs thousands of
  simulations to work out exactly how big it needs to be.

If you'd warned me at the start it would need this many small fixes
mid-tournament, I'd have believed you — and built it exactly the same way
anyway.

If you'd like to poke at the actual code — the scripts, the components, the
occasional embarrassing commit message — it's all on
[GitHub](https://github.com/rjeans/wc2026-sweepstake).

That's the lot: a static site, some text files, a few scripts, a robot that
runs every half hour, and an AI doing the actual typing while I supply the
opinions. Calm, cheap and — most of the time — quietly correct.
