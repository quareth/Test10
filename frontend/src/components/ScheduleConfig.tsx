import { useState } from "react";
import type { Schedule } from "../types";
import {
  createOrUpdateSchedule,
  deleteSchedule,
  toggleSchedule,
} from "../api";
import StatusBadge from "./StatusBadge";
import LoadingSpinner from "./LoadingSpinner";

interface ScheduleConfigProps {
  targetId: number;
  schedule: Schedule | null;
  onScheduleChange: () => void;
}

const INTERVAL_OPTIONS = [
  { value: "6h", label: "Every 6 hours" },
  { value: "12h", label: "Every 12 hours" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "cron", label: "Custom (cron)" },
] as const;

function intervalLabel(intervalType: string): string {
  const option = INTERVAL_OPTIONS.find((o) => o.value === intervalType);
  return option ? option.label : intervalType;
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const target = new Date(dateStr).getTime();
  const diffMs = target - now;
  const absDiff = Math.abs(diffMs);
  const isPast = diffMs < 0;

  const minutes = Math.floor(absDiff / 60_000);
  const hours = Math.floor(absDiff / 3_600_000);
  const days = Math.floor(absDiff / 86_400_000);

  let relative: string;
  if (minutes < 1) {
    relative = "less than a minute";
  } else if (minutes < 60) {
    relative = `${minutes} minute${minutes === 1 ? "" : "s"}`;
  } else if (hours < 24) {
    relative = `${hours} hour${hours === 1 ? "" : "s"}`;
  } else {
    relative = `${days} day${days === 1 ? "" : "s"}`;
  }

  return isPast ? `${relative} ago` : `in ${relative}`;
}

function formatAbsoluteTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

export default function ScheduleConfig({
  targetId,
  schedule,
  onScheduleChange,
}: ScheduleConfigProps) {
  const [intervalType, setIntervalType] = useState("daily");
  const [cronExpression, setCronExpression] = useState("");
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cronError, setCronError] = useState<string | null>(null);

  const validateCron = (expr: string): boolean => {
    const parts = expr.trim().split(/\s+/);
    if (parts.length !== 5) {
      setCronError("Cron expression must have exactly 5 fields (e.g., 0 */6 * * *)");
      return false;
    }
    setCronError(null);
    return true;
  };

  const handleCreate = async () => {
    setError(null);
    if (intervalType === "cron") {
      if (!cronExpression.trim()) {
        setCronError("Cron expression is required for custom schedule");
        return;
      }
      if (!validateCron(cronExpression)) return;
    }

    setSaving(true);
    try {
      const data: { interval_type: string; cron_expression?: string } = {
        interval_type: intervalType,
      };
      if (intervalType === "cron") {
        data.cron_expression = cronExpression.trim();
      }
      await createOrUpdateSchedule(targetId, data);
      onScheduleChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save schedule");
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async () => {
    if (!schedule) return;
    setToggling(true);
    setError(null);
    try {
      const newStatus = schedule.status === "active" ? "paused" : "active";
      await toggleSchedule(targetId, newStatus);
      onScheduleChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update schedule");
    } finally {
      setToggling(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteSchedule(targetId);
      setConfirmDelete(false);
      onScheduleChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete schedule");
    } finally {
      setDeleting(false);
    }
  };

  // Empty state: no schedule exists
  if (!schedule) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "var(--space-6)",
            gap: "var(--space-4)",
            color: "var(--color-neutral-500)",
          }}
        >
          <p style={{ margin: 0, fontSize: "var(--font-size-lg)" }}>
            No schedule configured
          </p>
          <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>
            Set up automatic scraping on a recurring schedule.
          </p>
        </div>

        {/* Create form */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-4)",
            padding: "var(--space-4)",
            backgroundColor: "var(--color-neutral-50)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <div className="form-group">
            <label className="form-label" htmlFor="schedule-interval">
              Scrape interval
            </label>
            <select
              id="schedule-interval"
              className="form-input"
              value={intervalType}
              onChange={(e) => {
                setIntervalType(e.target.value);
                setCronError(null);
              }}
            >
              {INTERVAL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {intervalType === "cron" && (
            <div className="form-group">
              <label className="form-label" htmlFor="cron-expression">
                Cron expression
              </label>
              <input
                id="cron-expression"
                className="form-input"
                type="text"
                placeholder="0 */6 * * *"
                value={cronExpression}
                onChange={(e) => {
                  setCronExpression(e.target.value);
                  if (cronError) setCronError(null);
                }}
              />
              {cronError && (
                <span
                  className="error-alert"
                  style={{ marginTop: "var(--space-1)" }}
                >
                  {cronError}
                </span>
              )}
              <span
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-neutral-400)",
                  marginTop: "var(--space-1)",
                }}
              >
                5-field format: minute hour day-of-month month day-of-week
              </span>
            </div>
          )}

          {error && (
            <p className="error-alert" style={{ margin: 0 }}>
              {error}
            </p>
          )}

          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={saving}
          >
            {saving ? "Saving..." : "Set Up Schedule"}
          </button>
        </div>
      </div>
    );
  }

  // Existing schedule view
  const isActive = schedule.status === "active";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-5)",
      }}
    >
      {/* Status and interval header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "var(--space-3)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
          }}
        >
          <StatusBadge status={schedule.status} />
          <span
            style={{
              fontSize: "var(--font-size-base)",
              fontWeight: "var(--font-weight-medium)",
              color: "var(--color-neutral-700)",
            }}
          >
            {intervalLabel(schedule.interval_type)}
          </span>
          {schedule.interval_type === "cron" && schedule.cron_expression && (
            <code
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-neutral-500)",
                backgroundColor: "var(--color-neutral-100)",
                padding: "var(--space-1) var(--space-2)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              {schedule.cron_expression}
            </code>
          )}
        </div>
      </div>

      {/* Schedule details */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
          fontSize: "var(--font-size-sm)",
          color: "var(--color-neutral-600)",
        }}
      >
        {schedule.next_run_at && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
            }}
          >
            <span style={{ fontWeight: "var(--font-weight-medium)" }}>
              Next run:
            </span>
            <span>{formatRelativeTime(schedule.next_run_at)}</span>
            <span style={{ color: "var(--color-neutral-400)" }}>
              ({formatAbsoluteTime(schedule.next_run_at)})
            </span>
          </div>
        )}

        {schedule.last_run_at && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontWeight: "var(--font-weight-medium)" }}>
              Last run:
            </span>
            <span>{formatRelativeTime(schedule.last_run_at)}</span>
            <span style={{ color: "var(--color-neutral-400)" }}>
              ({formatAbsoluteTime(schedule.last_run_at)})
            </span>
            {schedule.last_run_status && (
              <StatusBadge status={schedule.last_run_status} />
            )}
          </div>
        )}
      </div>

      {/* Change interval */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
          padding: "var(--space-4)",
          backgroundColor: "var(--color-neutral-50)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <span
          style={{
            fontSize: "var(--font-size-sm)",
            fontWeight: "var(--font-weight-medium)",
            color: "var(--color-neutral-700)",
          }}
        >
          Change interval
        </span>
        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            alignItems: "flex-end",
            flexWrap: "wrap",
          }}
        >
          <div className="form-group" style={{ flex: 1, minWidth: 160 }}>
            <select
              className="form-input"
              value={intervalType}
              onChange={(e) => {
                setIntervalType(e.target.value);
                setCronError(null);
              }}
            >
              {INTERVAL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          {intervalType === "cron" && (
            <div className="form-group" style={{ flex: 1, minWidth: 180 }}>
              <input
                className="form-input"
                type="text"
                placeholder="0 */6 * * *"
                value={cronExpression}
                onChange={(e) => {
                  setCronExpression(e.target.value);
                  if (cronError) setCronError(null);
                }}
              />
            </div>
          )}
          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={saving}
            style={{ whiteSpace: "nowrap" }}
          >
            {saving ? "Saving..." : "Update"}
          </button>
        </div>
        {cronError && (
          <span className="error-alert">{cronError}</span>
        )}
      </div>

      {/* Action buttons */}
      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          flexWrap: "wrap",
        }}
      >
        {/* Pause/Resume toggle */}
        <button
          className={`btn ${isActive ? "btn-secondary" : "btn-primary"}`}
          onClick={handleToggle}
          disabled={toggling}
        >
          {toggling
            ? "Updating..."
            : isActive
              ? "Pause Schedule"
              : "Resume Schedule"}
        </button>

        {/* Delete with confirmation */}
        {!confirmDelete ? (
          <button
            className="btn btn-danger"
            onClick={() => setConfirmDelete(true)}
          >
            Delete Schedule
          </button>
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
              padding: "var(--space-3) var(--space-4)",
              backgroundColor: "var(--color-accent-error-bg)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <span
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-accent-error-text)",
                fontWeight: "var(--font-weight-medium)",
              }}
            >
              Delete this schedule?
            </span>
            <button
              className="btn btn-danger"
              onClick={handleDelete}
              disabled={deleting}
              style={{ padding: "var(--space-1) var(--space-3)" }}
            >
              {deleting ? "Deleting..." : "Confirm"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setConfirmDelete(false)}
              style={{ padding: "var(--space-1) var(--space-3)" }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* Loading indicator for async ops */}
      {(saving || toggling || deleting) && (
        <LoadingSpinner />
      )}

      {error && (
        <p className="error-alert" style={{ margin: 0 }}>
          {error}
        </p>
      )}
    </div>
  );
}
