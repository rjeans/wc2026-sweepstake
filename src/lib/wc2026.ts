import { readFileSync, existsSync, statSync } from 'fs';
import { resolve } from 'path';

const DATA_DIR = './src/data';

export const PLAYERS = ['Richard', 'Nichola', 'Emily', 'Henry', 'Sophie', 'Tega', 'Pete', 'Ella'] as const;
export type PlayerName = (typeof PLAYERS)[number];
export const playerSlug = (name: string) => name.toLowerCase();

const GROUP_WIN = 3;
const GROUP_DRAW = 1;

// Linear tournament path (advancement/depth). 'THIRD' is NOT here: it branches
// off the semi-final. It's a valid Stage value (see below) but never a step.
export const STAGE_ORDER = ['GROUP', 'R32', 'R16', 'QF', 'SF', 'FINAL', 'CHAMPION'] as const;
export type Stage = (typeof STAGE_ORDER)[number] | 'THIRD';
// The linear ladder only (excludes THIRD) — used for depth/advancement.
export type LinearStage = (typeof STAGE_ORDER)[number];

// Third-place play-off winner: semi-final depth + this bonus (mirrors scoring.py).
export const THIRD_BONUS = 20;

const STAGE_LABEL: Record<Stage, string> = {
  GROUP: 'Group',
  R32: 'Round of 32',
  R16: 'Round of 16',
  QF: 'Quarter-final',
  SF: 'Semi-final',
  THIRD: 'Third place',
  FINAL: 'Final',
  CHAMPION: 'Champion',
};

// Cumulative progression bonus a team keeps once it reaches a round. Mirrors the
// cumulative of INCREMENT in scoring.py — keep the two in sync. THIRD = SF + 20.
export const STAGE_BONUS: Record<Stage, number> = {
  GROUP: 0,
  R32: 5,
  R16: 10,
  QF: 20,
  SF: 40,
  THIRD: 60,
  FINAL: 80,
  CHAMPION: 160,
};

export interface Team {
  group: string;
  group_rank: number;
  country: string;
  fifa_rank: number;
}

export interface TeamRow extends Team {
  owner: string | null;
  tier: number;
  gw: number;
  gd: number;
  gl: number;
  gf: number;
  ga: number;
  groupPoints: number;
  points: number; // total contribution to owner's score: group points + progression bonus
  stage: Stage;
  koReached: Stage; // deepest knockout round the team appears in the fixtures (GROUP = not through)
  eliminated: boolean; // out of the tournament: lost a knockout tie, or didn't escape the group
  // Played/won/drawn/lost/goals across ALL matches (group + completed knockout).
  record: { p: number; w: number; d: number; l: number; gf: number; ga: number };
}

export interface PlayerRow {
  rank: number;
  name: string;
  played: number; // total matches played across the player's six teams
  points: number;
  gf: number;
  gd: number;
  best: Stage;
  teams: TeamRow[]; // sorted by tier ascending; empty pre-draw
}

export type MatchStatus = 'pre' | 'in' | 'post';

export interface Match {
  date: string; // ISO date, e.g. 2026-06-11
  stage: Stage;
  group: string; // group letter for group games; '' for knockouts
  home: string;
  away: string;
  homeScore: number | null; // null = not yet played
  awayScore: number | null;
  status: MatchStatus; // 'in' means currently being played
  winner: string | null; // actual winner incl. penalty shootouts; null until decided
}

export type TournamentStatus =
  | 'pre-draw'
  | 'pre-tournament'
  | 'in-progress'
  | 'complete';

export interface TournamentData {
  status: TournamentStatus;
  teams: TeamRow[];
  players: PlayerRow[];
  matches: Match[]; // chronological; empty until a matches.csv is synced
  liveMatches: Match[]; // any matches currently in progress
  updatedAt: number; // epoch ms of the most recent data file
}

interface StandingsRow {
  rank: number;
  person: string;
  points: number;
  goals_for: number;
  goal_diff: number;
  best_run: Stage;
}

function parseCsv(path: string): Record<string, string>[] {
  const text = readFileSync(path, 'utf-8');
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  const header = lines[0].split(',').map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cells = line.split(',').map((c) => c.trim());
    const row: Record<string, string> = {};
    header.forEach((h, i) => {
      row[h] = cells[i] ?? '';
    });
    return row;
  });
}

function loadTeams(): Team[] {
  return parseCsv(resolve(DATA_DIR, 'teams.csv')).map((r) => ({
    group: r.group,
    group_rank: parseInt(r.group_rank),
    country: r.country,
    fifa_rank: parseInt(r.fifa_rank),
  }));
}

function loadAllocation(): Map<string, string> | null {
  const path = resolve(DATA_DIR, 'allocation.csv');
  if (!existsSync(path)) return null;
  const m = new Map<string, string>();
  for (const r of parseCsv(path)) m.set(r.country, r.person);
  return m;
}

interface ResultRow {
  gw: number;
  gd: number;
  gl: number;
  gf: number;
  ga: number;
  stage: Stage;
}

function loadResults(): Map<string, ResultRow> | null {
  const path = resolve(DATA_DIR, 'results.csv');
  if (!existsSync(path)) return null;
  const m = new Map<string, ResultRow>();
  for (const r of parseCsv(path)) {
    const stage: Stage =
      (STAGE_ORDER as readonly string[]).includes(r.stage) || r.stage === 'THIRD'
        ? (r.stage as Stage)
        : 'GROUP';
    m.set(r.country, {
      gw: parseInt(r.gw) || 0,
      gd: parseInt(r.gd) || 0,
      gl: parseInt(r.gl) || 0,
      gf: parseInt(r.gf) || 0,
      ga: parseInt(r.ga) || 0,
      stage,
    });
  }
  return m;
}

function loadStandings(): StandingsRow[] | null {
  const path = resolve(DATA_DIR, 'standings.csv');
  if (!existsSync(path)) return null;
  return parseCsv(path).map((r) => ({
    rank: parseInt(r.rank),
    person: r.person,
    points: parseInt(r.points),
    goals_for: parseInt(r.goals_for),
    goal_diff: parseInt(r.goal_diff),
    best_run: r.best_run as Stage,
  }));
}

function loadMatches(): Match[] {
  const path = resolve(DATA_DIR, 'matches.csv');
  if (!existsSync(path)) return [];
  const toScore = (v: string): number | null => {
    if (v === undefined || v.trim() === '') return null;
    const n = parseInt(v);
    return Number.isNaN(n) ? null : n;
  };
  return parseCsv(path).map((r) => {
    const status: MatchStatus =
      r.status === 'in' || r.status === 'post' ? r.status : 'pre';
    return {
      date: r.date ?? '',
      stage: (STAGE_ORDER as readonly string[]).includes(r.stage) || r.stage === 'THIRD'
        ? (r.stage as Stage)
        : 'GROUP',
      group: r.group ?? '',
      home: r.home,
      away: r.away,
      homeScore: toScore(r.home_score),
      awayScore: toScore(r.away_score),
      status,
      winner: r.winner && r.winner.trim() ? r.winner.trim() : null,
    };
  });
}

// Most recent modification time across the synced data files, so the page can
// show an honest "last updated" stamp.
function dataUpdatedAt(): number {
  let latest = 0;
  for (const name of ['teams.csv', 'allocation.csv', 'results.csv', 'standings.csv', 'matches.csv']) {
    const path = resolve(DATA_DIR, name);
    if (existsSync(path)) latest = Math.max(latest, statSync(path).mtimeMs);
  }
  return latest;
}

export function getTournamentData(): TournamentData {
  const teams = loadTeams();
  const allocation = loadAllocation();
  const results = loadResults();
  const standings = loadStandings();
  const matches = loadMatches();

  const teamsPlayed =
    results !== null &&
    Array.from(results.values()).some(
      (r) => r.gw + r.gd + r.gl > 0 || r.stage !== 'GROUP',
    );
  const champion =
    results !== null &&
    Array.from(results.values()).some((r) => r.stage === 'CHAMPION');

  let status: TournamentStatus = 'pre-draw';
  if (allocation) status = 'pre-tournament';
  if (allocation && teamsPlayed) status = 'in-progress';
  if (allocation && champion) status = 'complete';

  // Tier = which of six strength bands a team falls in (1 = strongest 8).
  const tierByCountry = new Map<string, number>();
  [...teams]
    .sort((a, b) => a.fifa_rank - b.fifa_rank)
    .forEach((t, i) => tierByCountry.set(t.country, Math.floor(i / 8) + 1));

  // Deepest knockout round each team appears in across the published fixtures.
  // This reflects qualification as soon as the bracket is drawn, before the
  // results-derived `stage` catches up. GROUP = not (yet) through.
  const koByCountry = new Map<string, LinearStage>();
  const creditKo = (c: string, s: LinearStage) => {
    const cur = koByCountry.get(c);
    if (!cur || STAGE_ORDER.indexOf(s) > STAGE_ORDER.indexOf(cur)) koByCountry.set(c, s);
  };
  // Win/draw/loss/goals from completed knockout matches, added to group records.
  type Rec = { p: number; w: number; d: number; l: number; gf: number; ga: number };
  const koStats = new Map<string, Rec>();
  const bumpKo = (c: string, gf: number, ga: number) => {
    const s = koStats.get(c) ?? { p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0 };
    s.p += 1; s.gf += gf; s.ga += ga;
    if (gf > ga) s.w += 1; else if (gf < ga) s.l += 1; else s.d += 1;
    koStats.set(c, s);
  };
  // Teams knocked out in the bracket: the beaten side of a decided knockout tie.
  const koEliminated = new Set<string>();
  // Winner of the third-place play-off: banks +20 on top of a semi-final exit.
  const thirdPlaceWinners = new Set<string>();
  for (const m of matches) {
    if (m.stage === 'GROUP') continue;
    if (m.stage === 'THIRD') {
      // Not a progression step: only the winner banks the bonus, nobody advances.
      // Live leader banks it provisionally; stats/elimination settle at full-time.
      const decided = m.status === 'post';
      if ((decided || m.status === 'in') && m.homeScore !== null && m.awayScore !== null) {
        if (decided) {
          bumpKo(m.home, m.homeScore, m.awayScore);
          bumpKo(m.away, m.awayScore, m.homeScore);
        }
        const w = m.winner ?? (m.homeScore > m.awayScore ? m.home : m.awayScore > m.homeScore ? m.away : null);
        if (w) {
          thirdPlaceWinners.add(w);
          if (decided) koEliminated.add(w === m.home ? m.away : m.home);
        }
      }
      continue;
    }
    // THIRD is handled above, so m.stage is a linear ladder stage here.
    const linearStage = m.stage as LinearStage;
    const i = STAGE_ORDER.indexOf(linearStage);
    // Both teams have reached this round; a completed win advances the winner.
    creditKo(m.home, linearStage);
    creditKo(m.away, linearStage);
    const decided = m.status === 'post';
    if ((decided || m.status === 'in') && m.homeScore !== null && m.awayScore !== null) {
      // Match stats and elimination only settle at full-time; but the leader of a
      // live tie advances provisionally, so the table tracks in-play knockout
      // results the same way the odds do (a level live score has no leader).
      if (decided) {
        bumpKo(m.home, m.homeScore, m.awayScore);
        bumpKo(m.away, m.awayScore, m.homeScore);
      }
      // Prefer the recorded winner (covers penalty shootouts on a level score).
      const winner =
        m.winner ?? (m.homeScore > m.awayScore ? m.home : m.awayScore > m.homeScore ? m.away : null);
      if (winner) {
        if (i + 1 < STAGE_ORDER.length) creditKo(winner, STAGE_ORDER[i + 1]);
        // A beaten semi-finalist is NOT out: they drop into the third-place
        // play-off (worth +20 if they win it), so don't grey them yet. The
        // fourth-placed team is greyed when that play-off is decided (above).
        if (decided && m.stage !== 'SF') koEliminated.add(winner === m.home ? m.away : m.home);
      }
    }
  }

  const teamRows: TeamRow[] = teams.map((t) => {
    const result = results?.get(t.country);
    const stage: Stage = result?.stage ?? 'GROUP';
    const gw = result?.gw ?? 0;
    const gd = result?.gd ?? 0;
    const gl = result?.gl ?? 0;
    const gf = result?.gf ?? 0;
    const ga = result?.ga ?? 0;
    const groupPoints = gw * GROUP_WIN + gd * GROUP_DRAW;
    // Deepest round actually reached = the deeper of the results-derived stage
    // and the bracket appearance. Reaching a round (incl. qualifying for the
    // R32) banks its progression bonus immediately, before results catch up.
    const bracket = koByCountry.get(t.country) ?? 'GROUP';
    // Depth is a linear-ladder concept: a third-place finish reads as a semi-
    // final exit, and its +20 is added separately below (thirdPlaceWinners).
    const wonThird = thirdPlaceWinners.has(t.country) || stage === 'THIRD';
    const depthStage: LinearStage = stage === 'THIRD' ? 'SF' : (stage as LinearStage);
    const reached: LinearStage =
      STAGE_ORDER.indexOf(bracket) > STAGE_ORDER.indexOf(depthStage) ? bracket : depthStage;
    const ko = koStats.get(t.country) ?? { p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0 };
    return {
      ...t,
      owner: allocation?.get(t.country) ?? null,
      tier: tierByCountry.get(t.country) ?? 0,
      gw,
      gd,
      gl,
      gf,
      ga,
      groupPoints,
      points: groupPoints + STAGE_BONUS[reached] + (wonThird ? THIRD_BONUS : 0),
      stage,
      koReached: reached,
      eliminated:
        koEliminated.has(t.country) ||
        ((status === 'in-progress' || status === 'complete') && reached === 'GROUP'),
      record: {
        p: gw + gd + gl + ko.p,
        w: gw + ko.w,
        d: gd + ko.d,
        l: gl + ko.l,
        gf: gf + ko.gf,
        ga: ga + ko.ga,
      },
    };
  });
  teamRows.sort((a, b) => a.fifa_rank - b.fifa_rank);

  const teamsByOwner = new Map<string, TeamRow[]>();
  for (const p of PLAYERS) teamsByOwner.set(p, []);
  for (const t of teamRows) {
    if (t.owner) teamsByOwner.get(t.owner)?.push(t);
  }
  for (const list of teamsByOwner.values()) list.sort((a, b) => a.tier - b.tier);

  const standingsByName = new Map(standings?.map((s) => [s.person, s]) ?? []);
  const playerRows: PlayerRow[] = PLAYERS.map((name) => {
    const s = standingsByName.get(name);
    const owned = teamsByOwner.get(name) ?? [];
    const played = owned.reduce((sum, t) => sum + t.record.p, 0);
    return {
      rank: 0,
      name,
      played,
      points: s?.points ?? 0,
      gf: s?.goals_for ?? 0,
      gd: s?.goal_diff ?? 0,
      best: (s?.best_run ?? 'GROUP') as Stage,
      teams: owned,
    };
  });

  if (status === 'in-progress' || status === 'complete') {
    playerRows.sort((a, b) => {
      if (b.points !== a.points) return b.points - a.points;
      if (b.gd !== a.gd) return b.gd - a.gd;
      if (b.gf !== a.gf) return b.gf - a.gf;
      return a.name.localeCompare(b.name);
    });
  } else {
    // Pre-draw / pre-tournament: everyone is tied at zero, so sort alphabetically.
    playerRows.sort((a, b) => a.name.localeCompare(b.name));
  }
  playerRows.forEach((p, i) => {
    p.rank = i + 1;
  });

  const liveMatches = matches.filter((m) => m.status === 'in');
  return { status, teams: teamRows, players: playerRows, matches, liveMatches, updatedAt: dataUpdatedAt() };
}

export function stageLabel(s: Stage): string {
  return STAGE_LABEL[s];
}
