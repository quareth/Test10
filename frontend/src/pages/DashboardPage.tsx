import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { getTargets, createTarget, deleteTarget } from "../api";
import type { Target } from "../types";
import LoadingSpinner from "../components/LoadingSpinner";
import EmptyState from "../components/EmptyState";
import StatusBadge from "../components/StatusBadge";

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const target = new Date(dateStr).getTime();
  const diffMs = target - now;
  if (diffMs <= 0) return "due now";
  const diffMin = Math.round(diffMs / 60_000);
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHrs = Math.round(diffMs / 3_600_000);
  if (diffHrs < 24) return `in ${diffHrs}h`;
  const diffDays = Math.round(diffMs / 86_400_000);
  return `in ${diffDays}d`;
}

function scheduleLabel(status: string | null): string | null {
  if (status === "active") return "Scheduled";
  if (status === "paused") return "Paused";
  return null;
}

const SCHEDULE_COLORS: Record<string, { bg: string; text: string }> = {
  active: { bg: "var(--color-secondary)", text: "var(--color-secondary-text)" },
  paused: { bg: "var(--color-neutral-200)", text: "var(--color-neutral-700)" },
};

export default function DashboardPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newName, setNewName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [addLoading, setAddLoading] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  useEffect(() => {
    getTargets()
      .then((data) => {
        setTargets(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load targets");
        setLoading(false);
      });
  }, []);

  async function handleAddTarget(e: React.FormEvent) {
    e.preventDefault();
    if (!newUrl.trim() || !newName.trim()) {
      setAddError("Both URL and name are required.");
      return;
    }
    setAddLoading(true);
    setAddError(null);
    try {
      const target = await createTarget(newUrl.trim(), newName.trim());
      setTargets((prev) => [target, ...prev]);
      setNewUrl("");
      setNewName("");
      setShowAddForm(false);
    } catch (err) {
      setAddError(
        err instanceof Error ? err.message : "Failed to create target",
      );
    } finally {
      setAddLoading(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteTarget(id);
      setTargets((prev) => prev.filter((t) => t.id !== id));
      setDeleteConfirmId(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete target",
      );
      setDeleteConfirmId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner message="Loading targets..." />;
  }

  if (error) {
    return (
      <div
        style={{
          padding: "var(--space-4)",
          textAlign: "center",
        }}
      >
        <p className="error-alert">{error}</p>
      </div>
    );
  }

  return (
    <section style={{ padding: "var(--space-6)" }}>
      <div className="page-header">
        <h1 style={{ margin: 0, fontSize: "var(--font-size-xl)" }}>
          Your Targets
        </h1>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowAddForm((v) => !v);
            setAddError(null);
          }}
        >
          {showAddForm ? "Cancel" : "Add Target"}
        </button>
      </div>

      {showAddForm && (
        <form
          onSubmit={handleAddTarget}
          className="card"
          style={{
            marginBottom: "var(--space-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-4)",
          }}
        >
          <div className="form-group">
            <label htmlFor="target-url" className="form-label">
              URL
            </label>
            <input
              id="target-url"
              type="url"
              className="form-input"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://example.com/sitemap.xml"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="target-name" className="form-label">
              Name
            </label>
            <input
              id="target-name"
              type="text"
              className="form-input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="My Website"
              required
            />
          </div>
          {addError && (
            <p className="error-alert" style={{ margin: 0 }}>
              {addError}
            </p>
          )}
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={addLoading}
            >
              {addLoading ? "Adding..." : "Add Target"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setShowAddForm(false);
                setAddError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {targets.length === 0 ? (
        <EmptyState
          message="No targets yet."
          actionLabel="Add Target"
          onAction={() => setShowAddForm(true)}
        />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "var(--space-4)",
          }}
        >
          {targets.map((target) => (
            <Link
              key={target.id}
              to={`/targets/${target.id}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div
                className="card card-interactive"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--space-2)",
                  cursor: "pointer",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <h3
                    style={{
                      margin: 0,
                      fontSize: "var(--font-size-base)",
                      fontWeight: "var(--font-weight-bold)",
                    }}
                  >
                    {target.name}
                  </h3>
                  {target.last_job_status && (
                    <StatusBadge status={target.last_job_status} />
                  )}
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-neutral-500)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {target.url}
                </p>
                {target.has_schedule && target.schedule_status && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      marginTop: "var(--space-1)",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px var(--space-2)",
                        borderRadius: "9999px",
                        backgroundColor:
                          (SCHEDULE_COLORS[target.schedule_status] ?? SCHEDULE_COLORS.paused).bg,
                        color:
                          (SCHEDULE_COLORS[target.schedule_status] ?? SCHEDULE_COLORS.paused).text,
                        fontSize: "var(--font-size-xs, 0.75rem)",
                        fontWeight: 500,
                        lineHeight: 1.4,
                      }}
                    >
                      {scheduleLabel(target.schedule_status)}
                    </span>
                    {target.schedule_status === "active" && target.next_run_at && (
                      <span
                        style={{
                          fontSize: "var(--font-size-xs, 0.75rem)",
                          color: "var(--color-neutral-400)",
                        }}
                      >
                        Next run: {formatRelativeTime(target.next_run_at)}
                      </span>
                    )}
                  </div>
                )}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginTop: "var(--space-2)",
                  }}
                >
                  <span
                    style={{
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-neutral-400)",
                    }}
                  >
                    {target.last_scraped_at
                      ? `Last scraped: ${new Date(target.last_scraped_at).toLocaleDateString()}`
                      : "Never scraped"}
                  </span>
                  {deleteConfirmId === target.id ? (
                    <span
                      style={{
                        display: "flex",
                        gap: "var(--space-2)",
                        alignItems: "center",
                      }}
                    >
                      <span
                        className="error-alert"
                      >
                        Delete?
                      </span>
                      <button
                        className="btn btn-danger"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          handleDelete(target.id);
                        }}
                        style={{
                          padding: "var(--space-1) var(--space-3)",
                          fontSize: "var(--font-size-sm)",
                        }}
                      >
                        Yes
                      </button>
                      <button
                        className="btn btn-secondary"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDeleteConfirmId(null);
                        }}
                        style={{
                          padding: "var(--space-1) var(--space-3)",
                          fontSize: "var(--font-size-sm)",
                        }}
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <button
                      className="btn btn-secondary"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setDeleteConfirmId(target.id);
                      }}
                      style={{
                        padding: "var(--space-1) var(--space-3)",
                        color: "var(--color-error)",
                        fontSize: "var(--font-size-sm)",
                      }}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
