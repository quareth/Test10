import type { User, Target, ScrapeJob, Snapshot, Schedule } from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "Unauthorized");
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "Unknown error");
    throw new ApiError(response.status, text);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function login(
  username: string,
  password: string,
): Promise<User> {
  const data = await apiFetch<{ user: User }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  return data.user;
}

export async function logout(): Promise<void> {
  await apiFetch<{ ok: boolean }>("/api/auth/logout", {
    method: "POST",
  });
}

export async function getMe(): Promise<User> {
  const data = await apiFetch<{ user: User }>("/api/auth/me");
  return data.user;
}

export async function getTargets(): Promise<Target[]> {
  const data = await apiFetch<{ targets: Target[] }>("/api/targets");
  return data.targets;
}

export async function createTarget(
  url: string,
  name: string,
): Promise<Target> {
  const data = await apiFetch<{ target: Target }>("/api/targets", {
    method: "POST",
    body: JSON.stringify({ url, name }),
  });
  return data.target;
}

export async function deleteTarget(id: number): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/targets/${id}`, {
    method: "DELETE",
  });
}

export async function triggerScrape(targetId: number): Promise<ScrapeJob> {
  const data = await apiFetch<{ job: ScrapeJob }>(
    `/api/targets/${targetId}/scrape`,
    { method: "POST" },
  );
  return data.job;
}

export async function getJobs(targetId: number): Promise<ScrapeJob[]> {
  const data = await apiFetch<{ jobs: ScrapeJob[] }>(
    `/api/targets/${targetId}/jobs`,
  );
  return data.jobs;
}

export async function getJobStatus(jobId: number): Promise<ScrapeJob> {
  const data = await apiFetch<{ job: ScrapeJob }>(
    `/api/jobs/${jobId}/status`,
  );
  return data.job;
}

export async function getSnapshot(
  jobId: number,
): Promise<{ snapshot: Snapshot; files: string[] }> {
  return apiFetch<{ snapshot: Snapshot; files: string[] }>(
    `/api/jobs/${jobId}/snapshot`,
  );
}

export function getDownloadUrl(
  snapshotId: number,
  format: string,
  path?: string,
): string {
  const params = new URLSearchParams({ format });
  if (path) {
    params.set("path", path);
  }
  return `/api/snapshots/${snapshotId}/download?${params.toString()}`;
}

export async function getSchedule(
  targetId: number,
): Promise<Schedule | null> {
  try {
    const data = await apiFetch<{ schedule: Schedule }>(
      `/api/targets/${targetId}/schedule`,
    );
    return data.schedule;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function createOrUpdateSchedule(
  targetId: number,
  data: { interval_type: string; cron_expression?: string },
): Promise<Schedule> {
  const result = await apiFetch<{ schedule: Schedule }>(
    `/api/targets/${targetId}/schedule`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
  return result.schedule;
}

export async function deleteSchedule(targetId: number): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/targets/${targetId}/schedule`, {
    method: "DELETE",
  });
}

export async function toggleSchedule(
  targetId: number,
  status: "active" | "paused",
): Promise<Schedule> {
  const result = await apiFetch<{ schedule: Schedule }>(
    `/api/targets/${targetId}/schedule`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    },
  );
  return result.schedule;
}
