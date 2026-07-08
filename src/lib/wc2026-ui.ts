// Presentation helpers shared across the WC2026 sweepstake pages.
import type { Stage, TournamentStatus } from './wc2026';

export const STATUS_META: Record<TournamentStatus, { label: string; dot: string; live: boolean }> = {
  'pre-draw': { label: 'Draw pending', dot: '#fbbf24', live: false },
  'pre-tournament': { label: 'Draw complete', dot: '#38bdf8', live: false },
  'in-progress': { label: 'Live', dot: '#34d399', live: true },
  complete: { label: 'Complete', dot: '#a78bfa', live: false },
};

export const fmtSigned = (n: number) => (n > 0 ? `+${n}` : `${n}`);

// Each player keeps a signature colour everywhere they appear.
const PLAYER_COLORS: Record<string, string> = {
  Richard: '#2563eb',
  Nichola: '#dc2626',
  Emily: '#ea580c',
  Henry: '#16a34a',
  Sophie: '#0891b2',
  Tega: '#7c3aed',
  Pete: '#ca8a04',
  Ella: '#475569',
};
export const playerColor = (name: string) => PLAYER_COLORS[name] ?? '#475569';

// Strength tier 1 (strongest) -> 6 (weakest), rendered as a teal heat scale.
const TIER_BG = ['#0f766e', '#0d9488', '#14b8a6', '#5eead4', '#99f6e4', '#ccfbf1'];
const TIER_FG = ['#ffffff', '#ffffff', '#042f2e', '#042f2e', '#042f2e', '#042f2e'];
export const tierStyle = (tier: number) => {
  const i = Math.min(Math.max(tier - 1, 0), 5);
  return `background-color:${TIER_BG[i]};color:${TIER_FG[i]};`;
};

// Knockout depth, coloured warmer as it gets deeper; champion is gold.
const STAGE_BADGE: Record<Stage, { bg: string; fg: string }> = {
  GROUP: { bg: '#e2e8f0', fg: '#475569' },
  R32: { bg: '#dbeafe', fg: '#1d4ed8' },
  R16: { bg: '#cffafe', fg: '#0e7490' },
  QF: { bg: '#d1fae5', fg: '#047857' },
  SF: { bg: '#fef9c3', fg: '#a16207' },
  THIRD: { bg: '#fef3c7', fg: '#b45309' },
  FINAL: { bg: '#ffedd5', fg: '#c2410c' },
  CHAMPION: { bg: '#fde68a', fg: '#92400e' },
};
export const stageStyle = (s: Stage) => `background-color:${STAGE_BADGE[s].bg};color:${STAGE_BADGE[s].fg};`;

// Compact knockout label for inline "made the last 32 / 16 / …" badges.
const STAGE_SHORT: Record<Stage, string> = {
  GROUP: '', R32: 'R32', R16: 'R16', QF: 'QF', SF: 'SF', THIRD: '3rd', FINAL: 'Final', CHAMPION: 'Winner',
};
export const stageShort = (s: Stage) => STAGE_SHORT[s];

export const MEDALS = ['#e0aa3e', '#9ca3af', '#b87333'];

// Country -> ISO 3166-1 alpha-2 (flagcdn); UK home nations use the gb-* subdivisions.
const FLAG: Record<string, string> = {
  Mexico: 'mx', 'South Africa': 'za', 'South Korea': 'kr', Czechia: 'cz',
  Canada: 'ca', 'Bosnia-Herzegovina': 'ba', Qatar: 'qa', Switzerland: 'ch',
  Brazil: 'br', Morocco: 'ma', Haiti: 'ht', Scotland: 'gb-sct',
  'United States': 'us', Paraguay: 'py', Australia: 'au', 'Türkiye': 'tr',
  Germany: 'de', 'Curaçao': 'cw', 'Ivory Coast': 'ci', Ecuador: 'ec',
  Netherlands: 'nl', Japan: 'jp', Sweden: 'se', Tunisia: 'tn',
  Belgium: 'be', Egypt: 'eg', Iran: 'ir', 'New Zealand': 'nz',
  Spain: 'es', 'Cape Verde': 'cv', 'Saudi Arabia': 'sa', Uruguay: 'uy',
  France: 'fr', Senegal: 'sn', Iraq: 'iq', Norway: 'no',
  Argentina: 'ar', Algeria: 'dz', Austria: 'at', Jordan: 'jo',
  Portugal: 'pt', 'Congo DR': 'cd', Uzbekistan: 'uz', Colombia: 'co',
  England: 'gb-eng', Croatia: 'hr', Ghana: 'gh', Panama: 'pa',
};
export const flagCode = (country: string): string | null => FLAG[country] ?? null;
