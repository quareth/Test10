import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import LoadingSpinner from "../components/LoadingSpinner";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // Check if already authenticated. Use fetch directly to avoid
    // the 401 redirect built into apiFetch (which would cause a
    // reload loop on the login page).
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => {
        if (!cancelled && res.ok) {
          navigate("/", { replace: true });
        }
      })
      .catch(() => {
        // Not authenticated or network error -- show the form.
      })
      .finally(() => {
        if (!cancelled) {
          setCheckingSession(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message || "Login failed. Please try again.");
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession) {
    return <LoadingSpinner message="Checking session..." />;
  }

  return (
    <main
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="card"
        style={{
          width: "100%",
          maxWidth: 400,
          padding: "var(--space-6)",
        }}
      >
        <h1
          style={{
            margin: 0,
            marginBottom: "var(--space-6)",
            textAlign: "center",
            fontSize: "var(--font-size-xl)",
            color: "var(--color-neutral-900)",
          }}
        >
          Sign in
        </h1>

        {error && (
          <p role="alert" className="error-alert" style={{ margin: 0, marginBottom: "var(--space-4)" }}>
            {error}
          </p>
        )}

        <div className="form-group" style={{ marginBottom: "var(--space-4)" }}>
          <label htmlFor="username" className="form-label">
            Username
          </label>
          <input
            id="username"
            type="text"
            className="form-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
          />
        </div>

        <div className="form-group" style={{ marginBottom: "var(--space-6)" }}>
          <label htmlFor="password" className="form-label">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="form-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading}
          style={{ width: "100%" }}
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
