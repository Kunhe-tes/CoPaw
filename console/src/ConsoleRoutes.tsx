import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import ChatSharePage from "./pages/ChatShare";
import LoginPage from "./pages/Login";
import { authApi } from "./api/modules/auth";
import { getApiUrl, getApiToken, clearAuthToken } from "./api/config";
import { buildAuthHeaders } from "./api/authHeaders";
import { DynamicRenderProvider } from "./components/agentscope-chat/DynamicRenderContext";

function AuthGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"loading" | "auth-required" | "ok">(
    "loading",
  );

  useEffect(() => {
    // Token is already initialized at App level, no need to wait here
    let cancelled = false;
    (async () => {
      try {
        const res = await authApi.getStatus();
        if (cancelled) return;
        if (!res.enabled) {
          setStatus("ok");
          return;
        }
        const token = getApiToken();
        if (!token) {
          setStatus("auth-required");
          return;
        }
        try {
          const r = await fetch(getApiUrl("/auth/verify"), {
            headers: {
              Authorization: `Bearer ${token}`,
              ...buildAuthHeaders(),
            },
          });
          if (cancelled) return;
          if (r.ok) {
            setStatus("ok");
          } else {
            clearAuthToken();
            setStatus("auth-required");
          }
        } catch {
          if (!cancelled) {
            clearAuthToken();
            setStatus("auth-required");
          }
        }
      } catch {
        if (!cancelled) setStatus("ok");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") return null;
  if (status === "auth-required")
    return (
      <Navigate
        to={`/login?redirect=${encodeURIComponent(window.location.pathname)}`}
        replace
      />
    );
  return <>{children}</>;
}

// Keep Console pages and the chat template engine behind the non-Wealth route.
export default function ConsoleRoutes() {
  return (
    <DynamicRenderProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/chat-share/:token" element={<ChatSharePage />} />
        <Route
          path="/*"
          element={
            <AuthGuard>
              <MainLayout />
            </AuthGuard>
          }
        />
      </Routes>
    </DynamicRenderProvider>
  );
}
