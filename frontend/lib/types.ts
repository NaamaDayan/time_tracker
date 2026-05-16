export interface Segment {
  id: number;
  started_at: string;
  ended_at: string;
  activity_type: string;
  activity_label: string;
  color: string;
  source: string;
  confidence: number;
  metadata?: Record<string, unknown> | null;
}

export interface TimelineResponse {
  from: string;
  to: string;
  segments: Segment[];
  timezone: string;
}

/** Gap-merged activity window (Layer 3) for calendar display. */
export interface ActivityWindow {
  id: number;
  started_at: string;
  ended_at: string;
  activity_type: string;
  activity_label: string;
  color: string;
  confidence: number;
  sources: string[];
  segment_ids: number[];
  metadata?: Record<string, unknown> | null;
}

export interface WindowsResponse {
  from: string;
  to: string;
  windows: ActivityWindow[];
  timezone: string;
}

export interface ConfigResponse {
  timezone: string;
}

export interface ActivityType {
  slug: string;
  label: string;
  color: string;
}

export interface AggregateSlice {
  activity_type: string;
  label: string;
  color: string;
  seconds: number;
  percent: number;
}

export interface AggregateResponse {
  from: string;
  to: string;
  timezone: string;
  total_seconds: number;
  unattributed_seconds: number;
  slices: AggregateSlice[];
}

export type TimeWindowPreset = "day" | "week" | "month" | "year" | "custom";
