import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      navigate("/login");
    }
  }

  return (
    <>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "var(--space-4) var(--space-6)",
          backgroundColor: "var(--color-neutral-900)",
          color: "#fff",
        }}
      >
        <h1
          style={{
            margin: 0,
            fontSize: "var(--font-size-xl)",
            fontWeight: "var(--font-weight-bold)",
          }}
        >
          Sitemap Scraper
        </h1>
        <button
          className="btn btn-secondary"
          onClick={handleLogout}
          style={{
            color: "#fff",
            borderColor: "var(--color-neutral-400)",
            fontSize: "var(--font-size-sm)",
            padding: "var(--space-2) var(--space-4)",
          }}
        >
          Log out
        </button>
      </header>
      <main
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "var(--space-6)",
        }}
      >
        {children}
      </main>
    </>
  );
}
