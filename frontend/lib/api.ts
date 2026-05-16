import type {
  ActivityType,
  AggregateResponse,
  ConfigResponse,
  Segment,
  TimelineResponse,
  WindowsResponse,
} from "./types";

export interface SegmentCreateInput {
  started_at: string;
  ended_at: string;
  activity_type: string;
  title?: string | null;
  all_day?: boolean;
}

export interface SegmentUpdateInput {
  started_at?: string;
  ended_at?: string;
  activity_type?: string;
  title?: string | null;
  all_day?: boolean;
}

function apiBase(): string {
  if (typeof window === "undefined") {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return `${backend}/api/v1`;
  }
  return "/api/proxy";
}

function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window === "undefined") {
    headers["X-API-Key"] = process.env.API_KEY ?? "dev-only-change-me";
  }
  return headers;
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { ...apiHeaders(), ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const json = JSON.parse(text) as { detail?: string };
      if (json.detail) throw new Error(json.detail);
    } catch (e) {
      if (e instanceof SyntaxError) {
        throw new Error(text || `API error ${res.status}`);
      }
      throw e;
    }
    throw new Error(text || `API error ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export function getConfig(): Promise<ConfigResponse> {
  return fetchApi("/config");
}

export function getActivityTypes(): Promise<ActivityType[]> {
  return fetchApi("/activity-types");
}

export function getTimeline(from: string, to: string): Promise<TimelineResponse> {
  const params = new URLSearchParams({ from, to });
  return fetchApi(`/timeline?${params}`);
}

export function getWindows(from: string, to: string): Promise<WindowsResponse> {
  const params = new URLSearchParams({ from, to });
  return fetchApi(`/windows?${params}`);
}

export function getAggregate(
  from: string,
  to: string,
  types?: string[]
): Promise<AggregateResponse> {
  const params = new URLSearchParams({ from, to });
  if (types?.length) {
    params.set("types", types.join(","));
  }
  return fetchApi(`/aggregate?${params}`);
}

export interface SyncSourcesResult {
  since: string;
  raw_upserted: number;
  segments_written: number;
  entries_fetched: number;
  sources: Record<string, { entries_fetched?: number; raw_upserted?: number }>;
  errors: Record<string, string>;
}

export interface GoogleCalendarStatus {
  connected: boolean;
  email?: string | null;
}

export function getGoogleCalendarStatus(): Promise<GoogleCalendarStatus> {
  return fetchApi("/integrations/google/status");
}

export function syncSources(since = "7d"): Promise<SyncSourcesResult> {
  return fetchApi("/sync", {
    method: "POST",
    body: JSON.stringify({ since }),
  });
}

export function createSegment(body: SegmentCreateInput): Promise<Segment> {
  return fetchApi("/segments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSegment(id: number, body: SegmentUpdateInput): Promise<Segment> {
  return fetchApi(`/segments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteSegment(id: number): Promise<void> {
  return fetchApi(`/segments/${id}`, { method: "DELETE" });
}
