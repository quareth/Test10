export interface User {
  id: number;
  username: string;
}

export interface Target {
  id: number;
  url: string;
  name: string;
  created_at: string;
  last_job_status: string | null;
  last_scraped_at: string | null;
  has_schedule: boolean;
  schedule_status: string | null;
  next_run_at: string | null;
}

export interface ScrapeJob {
  id: number;
  target_id: number;
  status: string;
  pages_found: number;
  pages_scraped: number;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  trigger: "manual" | "scheduled";
}

export interface Schedule {
  id: number;
  target_id: number;
  interval_type: string;
  cron_expression: string | null;
  status: string;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface Snapshot {
  id: number;
  job_id: number;
  storage_path: string;
  file_count: number;
  total_size_bytes: number;
  created_at: string;
}
