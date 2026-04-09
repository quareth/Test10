import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api";
import LoadingSpinner from "./LoadingSpinner";

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then(() => {
        if (!cancelled) {
          setAuthenticated(true);
          setChecking(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          navigate("/login", { replace: true });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (checking) {
    return <LoadingSpinner message="Checking authentication..." />;
  }

  if (!authenticated) {
    return null;
  }

  return <>{children}</>;
}
