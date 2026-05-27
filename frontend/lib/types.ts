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
  calendar_days: number;
  total_seconds: number;
  unattributed_seconds: number;
  slices: AggregateSlice[];
}

export interface NetSlice {
  activity_type: string;
  label: string;
  color: string;
  seconds: number;
  percent: number;
}

export interface NetResponse {
  from: string;
  to: string;
  timezone: string;
  calendar_days: number;
  total_seconds: number;
  slices: NetSlice[];
}

export type TimeWindowPreset = "day" | "week" | "month" | "year" | "custom";

export type ZoneCategory =
  | "home"
  | "work"
  | "gym"
  | "family"
  | "social"
  | "transit"
  | "other";

export interface GpsZone {
  id: string;
  name: string;
  category: ZoneCategory;
  activity_type_slug: string | null;
  lat: number;
  lon: number;
  radius_meters: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GpsZoneCreateInput {
  name: string;
  category: ZoneCategory;
  lat: number;
  lon: number;
  radius_meters?: number;
  activity_type_slug?: string | null;
}

export interface GpsZoneUpdateInput {
  name?: string;
  category?: ZoneCategory;
  lat?: number;
  lon?: number;
  radius_meters?: number;
  activity_type_slug?: string | null;
  enabled?: boolean;
}

export interface ActivityRuleConfig {
  id: string;
  activity_type_slug: string;
  enabled: boolean;
  min_duration_minutes: number;
  merge_gap_minutes: number;
  boost_signals: Record<string, boolean>;
  custom_params: Record<string, unknown>;
  updated_at: string;
}

export interface ActivityRuleConfigUpdateInput {
  enabled?: boolean;
  min_duration_minutes?: number;
  merge_gap_minutes?: number;
  boost_signals?: Record<string, boolean>;
  custom_params?: Record<string, unknown>;
}

export interface PreviewSegment {
  id: number;
  started_at: string;
  ended_at: string;
  duration_minutes: number;
  source: string;
}

export interface PreviewResponse {
  segment_count: number;
  total_minutes: number;
  sample_segments: PreviewSegment[];
}
