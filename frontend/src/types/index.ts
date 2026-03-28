export interface Team {
  id: string;
  profile_id: string;
  name: string;
  color_primary: string | null;
  color_secondary: string | null;
  created_at: string;
}

export interface Profile {
  id: string;
  name: string;
  jersey_number: number | null;
  team_color_primary: string | null;
  team_color_secondary: string | null;
  photos: ProfilePhoto[];
  teams: Team[];
  created_at: string;
}

export interface ProfilePhoto {
  id: string;
  profile_id: string;
  file_key: string;
  is_primary: boolean;
  has_embedding: boolean;
  created_at: string;
}

export interface Video {
  id: string;
  title: string;
  opponent: string | null;
  game_date: string | null;
  file_key: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface ProcessingJob {
  id: string;
  video_id: string;
  profile_id: string;
  team_id: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  celery_task_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  events_count: number | null;
  highlights_count: number | null;
  created_at: string;
}

export interface Highlight {
  id: string;
  job_id: string;
  event_type: string;
  start_time: number;
  end_time: number;
  file_key: string | null;
  thumbnail_file_key: string | null;
  confidence: number | null;
  created_at: string;
}

export interface Stat {
  id: string;
  job_id: string;
  event_type: string;
  timestamp: number;
  court_x: number | null;
  court_y: number | null;
  created_at: string;
}

export interface StatsSummary {
  [event_type: string]: number;
}
