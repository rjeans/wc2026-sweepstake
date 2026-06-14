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
