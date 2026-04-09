import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getTargets,
  triggerScrape,
  getJobs,
  getJobStatus,
  getSnapshot,
  getDownloadUrl,
  getSchedule,
} from "../api";
import type { Target, ScrapeJob, Snapshot, Schedule } from "../types";
import LoadingSpinner from "../components/LoadingSpinner";
import EmptyState from "../components/EmptyState";
import StatusBadge from "../components/StatusBadge";
import ScheduleConfig from "../components/ScheduleConfig";
import TriggerBadge from "../components/TriggerBadge";

interface SnapshotData {
  snapshot: Snapshot;
  files: string[];
}

export default function TargetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const targetId = Number(id);

  const [target, setTarget] = useState<Target | null>(null);
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ScrapeJob | null>(null);
  const [snapshots, setSnapshots] = useState<Record<number, SnapshotData>>({});
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(true);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stop polling helper
  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Fetch snapshots for completed jobs
  const fetchSnapshotForJob = useCallback(
    async (jobId: number) => {
      if (snapshots[jobId]) return;
      try {
        const data = await getSnapshot(jobId);
        setSnapshots((prev) => ({ ...prev, [jobId]: data }));
      } catch {
        // Snapshot may not exist yet; silently ignore
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Fetch schedule data
  const fetchSchedule = useCallback(async () => {
    setScheduleLoading(true);
    try {
      const data = await getSchedule(targetId);
      setSchedule(data);
    } catch {
      // Schedule fetch failure is non-critical
    } finally {
      setScheduleLoading(false);
    }
  }, [targetId]);

  // Initial data load
  useEffect(() => {
    async function loadData() {
      try {
        const [allTargets, jobList] = await Promise.all([
          getTargets(),
          getJobs(targetId),
        ]);
        const found = allTargets.find((t) => t.id === targetId) ?? null;
        if (!found) {
          setError("Target not found.");
          setLoading(false);
          return;
        }
        setTarget(found);
        setJobs(jobList);

        // Find active job (pending or running)
        const active =
          jobList.find(
            (j) => j.status === "pending" || j.status === "running",
          ) ?? null;
        setActiveJob(active);

        // Eagerly fetch snapshots for completed jobs
        jobList
          .filter((j) => j.status === "complete")
          .forEach((j) => {
            fetchSnapshotForJob(j.id);
          });

        setLoading(false);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load target data",
        );
        setLoading(false);
      }
    }
    loadData();
    fetchSchedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetId]);

  // Polling for active job
  useEffect(() => {
    if (!activeJob) {
      stopPolling();
      return;
    }

    const poll = async () => {
      try {
        const updated = await getJobStatus(activeJob.id);
        if (updated.status === "complete" || updated.status === "failed") {
          stopPolling();
          setActiveJob(null);
          // Re-fetch jobs list
          const refreshedJobs = await getJobs(targetId);
          setJobs(refreshedJobs);
          // Fetch snapshot for completed job
          if (updated.status === "complete") {
            fetchSnapshotForJob(updated.id);
          }
        } else {
          setActiveJob(updated);
        }
      } catch {
        // Polling error; keep trying
      }
    };

    pollingRef.current = setInterval(poll, 2000);

    return () => {
      stopPolling();
    };
  }, [activeJob?.id, targetId, stopPolling, fetchSnapshotForJob]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const handleScrapeNow = async () => {
    setScrapeLoading(true);
    setScrapeError(null);
    try {
      const job = await triggerScrape(targetId);
      setJobs((prev) => [job, ...prev]);
      setActiveJob(job);
    } catch (err: unknown) {
      if (
        err &&
        typeof err === "object" &&
        "status" in err &&
        (err as { status: number }).status === 409
      ) {
        setScrapeError("A scrape is already in progress.");
      } else {
        setScrapeError(
          err instanceof Error ? err.message : "Failed to trigger scrape",
        );
      }
    } finally {
      setScrapeLoading(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading target..." />;
  }

  if (error || !target) {
    return (
      <section style={{ padding: "var(--space-6)" }}>
        <Link
          to="/"
          style={{
            textDecoration: "none",
            fontSize: "var(--font-size-sm)",
          }}
        >
          &larr; Back to Dashboard
        </Link>
        <div
          style={{
            padding: "var(--space-4)",
            textAlign: "center",
            marginTop: "var(--space-4)",
          }}
        >
          <p className="error-alert">{error ?? "Target not found."}</p>
        </div>
      </section>
    );
  }

  return (
    <section style={{ padding: "var(--space-6)", maxWidth: 900, margin: "0 auto" }}>
      {/* Back link */}
      <Link
        to="/"
        style={{
          textDecoration: "none",
          fontSize: "var(--font-size-sm)",
          display: "inline-block",
          marginBottom: "var(--space-4)",
        }}
      >
        &larr; Back to Dashboard
      </Link>

      {/* Target Info + Scrape Trigger */}
      <div
        className="card"
        style={{ marginBottom: "var(--space-6)" }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "var(--space-3)",
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <h1
              style={{
                margin: 0,
                fontSize: "var(--font-size-xl)",
                marginBottom: "var(--space-2)",
              }}
            >
              {target.name}
            </h1>
            <a
              href={target.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontSize: "var(--font-size-sm)",
                wordBreak: "break-all",
              }}
            >
              {target.url}
            </a>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleScrapeNow}
            disabled={!!activeJob || scrapeLoading}
            style={{ whiteSpace: "nowrap" }}
          >
            {scrapeLoading ? "Starting..." : "Scrape Now"}
          </button>
        </div>
        {scrapeError && (
          <p
            className="error-alert"
            style={{
              margin: 0,
              marginTop: "var(--space-3)",
            }}
          >
            {scrapeError}
          </p>
        )}
      </div>

      {/* Schedule Configuration */}
      <div
        className="card"
        style={{ marginBottom: "var(--space-6)" }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: "var(--font-size-base)",
            fontWeight: "var(--font-weight-bold)",
            marginBottom: "var(--space-4)",
          }}
        >
          Scheduled Scraping
        </h2>
        {scheduleLoading ? (
          <LoadingSpinner message="Loading schedule..." />
        ) : (
          <ScheduleConfig
            targetId={targetId}
            schedule={schedule}
            onScheduleChange={fetchSchedule}
          />
        )}
      </div>

      {/* Active Job Progress */}
      {activeJob && (
        <div
          className="card"
          style={{
            marginBottom: "var(--space-6)",
            border: "2px solid var(--color-secondary)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
              marginBottom: "var(--space-3)",
            }}
          >
            <h2
              style={{
                margin: 0,
                fontSize: "var(--font-size-base)",
                fontWeight: "var(--font-weight-bold)",
              }}
            >
              Active Scrape
            </h2>
            <StatusBadge status={activeJob.status} />
          </div>
          <div
            style={{
              display: "flex",
              gap: "var(--space-6)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-neutral-600)",
            }}
          >
            <span>
              Pages found: <strong>{activeJob.pages_found}</strong>
            </span>
            <span>
              Pages scraped: <strong>{activeJob.pages_scraped}</strong>
            </span>
          </div>
        </div>
      )}

      {/* Job History */}
      <h2
        style={{
          fontSize: "var(--font-size-base)",
          fontWeight: "var(--font-weight-bold)",
          marginBottom: "var(--space-4)",
        }}
      >
        Job History
      </h2>

      {jobs.length === 0 ? (
        <EmptyState
          message="No scrape jobs yet."
          actionLabel="Scrape Now"
          onAction={handleScrapeNow}
        />
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-4)",
          }}
        >
          {jobs.map((job) => {
            const snapshotData = snapshots[job.id];
            const isExpanded = expandedJobId === job.id;
            const isCompleted = job.status === "complete";

            return (
              <div key={job.id} className="card">
                {/* Job header */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "var(--space-2)",
                    marginBottom: "var(--space-3)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-3)",
                    }}
                  >
                    <StatusBadge status={job.status} />
                    <TriggerBadge trigger={job.trigger} />
                    <span
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-neutral-500)",
                      }}
                    >
                      Started:{" "}
                      {new Date(job.started_at).toLocaleString()}
                    </span>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      gap: "var(--space-4)",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-neutral-600)",
                    }}
                  >
                    <span>Found: {job.pages_found}</span>
                    <span>Scraped: {job.pages_scraped}</span>
                  </div>
                </div>

                {/* Completed at */}
                {job.completed_at && (
                  <p
                    style={{
                      margin: 0,
                      marginBottom: "var(--space-3)",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-neutral-400)",
                    }}
                  >
                    Completed:{" "}
                    {new Date(job.completed_at).toLocaleString()}
                  </p>
                )}

                {/* Error message */}
                {job.error_message && (
                  <p
                    className="error-alert"
                    style={{
                      margin: 0,
                      marginBottom: "var(--space-3)",
                    }}
                  >
                    Error: {job.error_message}
                  </p>
                )}

                {/* Download controls for completed jobs */}
                {isCompleted && snapshotData && (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-3)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: "var(--space-3)",
                        flexWrap: "wrap",
                        alignItems: "center",
                      }}
                    >
                      <a
                        href={getDownloadUrl(
                          snapshotData.snapshot.id,
                          "bulk",
                        )}
                        className="btn btn-secondary"
                        style={{
                          fontSize: "var(--font-size-sm)",
                          textDecoration: "none",
                          display: "inline-block",
                          padding: "var(--space-1) var(--space-4)",
                        }}
                      >
                        Download Bulk
                      </a>
                      <a
                        href={getDownloadUrl(
                          snapshotData.snapshot.id,
                          "structured_zip",
                        )}
                        className="btn btn-secondary"
                        style={{
                          fontSize: "var(--font-size-sm)",
                          textDecoration: "none",
                          display: "inline-block",
                          padding: "var(--space-1) var(--space-4)",
                        }}
                      >
                        Download ZIP
                      </a>
                      <button
                        className="btn btn-secondary"
                        onClick={() =>
                          setExpandedJobId(
                            isExpanded ? null : job.id,
                          )
                        }
                        style={{
                          fontSize: "var(--font-size-sm)",
                          padding: "var(--space-1) var(--space-4)",
                        }}
                      >
                        {isExpanded ? "Hide files" : "Show files"}
                      </button>
                    </div>

                    {/* Expanded file list */}
                    {isExpanded && (
                      <div
                        style={{
                          backgroundColor: "var(--color-neutral-50)",
                          borderRadius: "var(--radius-md)",
                          padding: "var(--space-4)",
                          maxHeight: 300,
                          overflowY: "auto",
                        }}
                      >
                        {snapshotData.files.length === 0 ? (
                          <p
                            style={{
                              margin: 0,
                              color: "var(--color-neutral-500)",
                              fontSize: "var(--font-size-sm)",
                            }}
                          >
                            No files in this snapshot.
                          </p>
                        ) : (
                          <ul
                            style={{
                              listStyle: "none",
                              margin: 0,
                              padding: 0,
                              display: "flex",
                              flexDirection: "column",
                              gap: "var(--space-2)",
                            }}
                          >
                            {snapshotData.files.map(
                              (filePath) => (
                                <li
                                  key={filePath}
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    gap: "var(--space-3)",
                                  }}
                                >
                                  <span
                                    style={{
                                      fontFamily: "monospace",
                                      fontSize:
                                        "var(--font-size-sm)",
                                      color:
                                        "var(--color-neutral-700)",
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                      minWidth: 0,
                                      flex: 1,
                                    }}
                                  >
                                    {filePath}
                                  </span>
                                  <a
                                    href={getDownloadUrl(
                                      snapshotData.snapshot.id,
                                      "file",
                                      filePath,
                                    )}
                                    style={{
                                      fontSize:
                                        "var(--font-size-sm)",
                                      textDecoration: "none",
                                      whiteSpace: "nowrap",
                                      flexShrink: 0,
                                    }}
                                  >
                                    Download
                                  </a>
                                </li>
                              ),
                            )}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
