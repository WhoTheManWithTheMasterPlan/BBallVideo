export interface Game {
  id: string;
  title: string;
  home_team: string;
  away_team: string;
  game_date: string;
  status: "uploaded" | "processing" | "completed" | "failed";
  duration_seconds: number | null;
  video_file_key: string | null;
  home_roster_id: string | null;
  away_roster_id: string | null;
  created_at: string;
}

export interface StatEvent {
  id: string;
  game_id: string;
  event_type: string;
  timestamp: number;
  player_id: string | null;
  team: string | null;
  court_x: number | null;
  court_y: number | null;
  created_at: string;
}

export interface Clip {
  id: string;
  game_id: string;
  event_type: string;
  start_time: number;
  end_time: number;
  file_key: string | null;
  thumbnail_file_key: string | null;
  player_id: string | null;
  created_at: string;
}

export interface GameSummary {
  game_id: string;
  teams: Record<
    string,
    {
      points: number;
      turnovers: number;
      made_shots: number;
      missed_shots: number;
    }
  >;
}

export interface RosterPlayer {
  id: string;
  roster_id: string;
  name: string;
  jersey_number: number;
  height_inches: number | null;
  position: string | null;
  photo_file_key: string | null;
  has_reid_embedding: boolean;
  created_at: string;
}

export interface Roster {
  id: string;
  team_name: string;
  season: string | null;
  jersey_color_primary: string | null;
  jersey_color_secondary: string | null;
  players: RosterPlayer[];
  created_at: string;
}
