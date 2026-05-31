import type {
  ActivityPriorityItem,
  ActivityPriorityPutItem,
  ActivityRuleConfig,
  ActivityRuleConfigUpdateInput,
  ActivityType,
  AggregateResponse,
  ConfigResponse,
  GpsZone,
  GpsZoneCreateInput,
  GpsZoneUpdateInput,
  NetResponse,
  PreviewResponse,
  Segment,
  TimelineResponse,
  ActivityWindow,
  ManualWindowInput,
  WindowPatchInput,
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

export function createActivityType(body: ActivityType): Promise<ActivityType> {
  return fetchApi("/activity-types", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getTimeline(from: string, to: string): Promise<TimelineResponse> {
  const params = new URLSearchParams({ from, to });
  return fetchApi(`/timeline?${params}`);
}

export interface GetWindowsOptions {
  includeDismissed?: boolean;
  minConfidence?: number;
}

export function getWindows(
  from: string,
  to: string,
  options?: GetWindowsOptions
): Promise<WindowsResponse> {
  const params = new URLSearchParams({ from, to });
  if (options?.includeDismissed) params.set("include_dismissed", "true");
  if (options?.minConfidence != null) {
    params.set("min_confidence", String(options.minConfidence));
  }
  return fetchApi(`/windows?${params}`);
}

export function patchWindow(id: number, body: WindowPatchInput): Promise<ActivityWindow> {
  return fetchApi(`/windows/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function createManualWindow(body: ManualWindowInput): Promise<ActivityWindow> {
  return fetchApi("/windows/manual", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteManualWindow(id: number): Promise<void> {
  return fetchApi(`/windows/manual/${id}`, { method: "DELETE" });
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

export function getNet(
  from: string,
  to: string,
  types?: string[]
): Promise<NetResponse> {
  const params = new URLSearchParams({ from, to });
  if (types?.length) {
    params.set("types", types.join(","));
  }
  return fetchApi(`/net?${params}`);
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

export function getZones(): Promise<GpsZone[]> {
  return fetchApi("/settings/zones/");
}

export function createZone(body: GpsZoneCreateInput): Promise<GpsZone> {
  return fetchApi("/settings/zones/", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateZone(id: string, body: GpsZoneUpdateInput): Promise<GpsZone> {
  return fetchApi(`/settings/zones/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteZone(id: string): Promise<void> {
  return fetchApi(`/settings/zones/${id}`, { method: "DELETE" });
}

export function getRuleConfigs(): Promise<ActivityRuleConfig[]> {
  return fetchApi("/settings/rule-configs/");
}

export function updateRuleConfig(
  slug: string,
  body: ActivityRuleConfigUpdateInput
): Promise<ActivityRuleConfig> {
  return fetchApi(`/settings/rule-configs/${slug}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function previewRuleConfig(
  slug: string,
  from?: string,
  to?: string
): Promise<PreviewResponse> {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return fetchApi(`/settings/rule-configs/${slug}/preview${qs ? `?${qs}` : ""}`);
}

export function getActivityPriority(): Promise<ActivityPriorityItem[]> {
  return fetchApi("/settings/activity-priority/");
}

export function putActivityPriority(
  body: ActivityPriorityPutItem[]
): Promise<ActivityPriorityItem[]> {
  return fetchApi("/settings/activity-priority/", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
