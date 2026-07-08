import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

const PRED_PATH = resolve('./src/data/predictions.json');

export interface PlayerPrediction {
  player: string;
  p_win: number;
  p_top3: number;
  expected_points: number;
  max_points_seen: number;
  p_owns_champion: number;
  odds_decimal: number | null;
  // Finishing-position distribution from the same sims: probability of each
  // place (index 0 = 1st), the single most likely place, the mean place, and
  // the shortest band of places holding >= position_ci_prob of the outcomes.
  position_probs: number[];
  most_likely_position: number;
  expected_position: number;
  position_ci: [number, number];
  position_ci_prob: number;
  delta_p_win?: number;
  delta_expected_points?: number;
  delta_odds_decimal?: number;
}

export interface TeamPrediction {
  country: string;
  owner: string | null;
  group: string;
  fifa_rank: number;
  p_qualify: number;
  p_r16: number;
  p_qf: number;
  p_sf: number;
  p_final: number;
  p_champion: number;
  expected_points: number;
  odds_decimal: number | null;
  delta_p_champion?: number;
  delta_expected_points?: number;
  delta_odds_decimal?: number;
}

export interface PredictionsData {
  generated_at: string;
  trials: number;
  locked_group_matches: number;
  locked_ko_matches: number;
  comparison_date: string | null;
  predictions: PlayerPrediction[];
  teams: TeamPrediction[];
}

export function loadPredictions(): PredictionsData | null {
  if (!existsSync(PRED_PATH)) return null;
  return JSON.parse(readFileSync(PRED_PATH, 'utf-8')) as PredictionsData;
}
