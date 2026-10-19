import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, clearToken, loadToken, saveToken } from "./api";
import { Layout } from "./components/Layout";
import { Button, ErrorText, Field, inputClass } from "./components/ui";
import { IncidentsPage } from "./pages/Incidents";
import { IncidentDetailPage } from "./pages/IncidentDetail";
import { InfrastructurePage } from "./pages/Infrastructure";
import { OverviewPage } from "./pages/Overview";
import { ReliabilityPage } from "./pages/Reliability";
import { ServicesPage } from "./pages/Services";
import { SettingsPage } from "./pages/Settings";
import type { Meta } from "./types";

interface Who {
  actor: string;
  role: string;
}

export function App() {
  const [token, setToken] = useState(loadToken);
  const session = useQuery({
    queryKey: ["whoami", token],
    queryFn: () => api<Who>("/api/v1/whoami", {}, token),
    enabled: token.length > 0,
  });

  if (!token || session.error) {
    return (
      <Login
        error={session.error}
        onSubmit={(value) => {
          saveToken(value);
          setToken(value);
        }}
      />
    );
  }
  if (session.isLoading || !session.data) {
    return <p className="p-8 text-sm text-muted">Checking credentials…</p>;
  }

  return (
    <Routes>
      <Route
        element={
          <Layout
            role={session.data.role}
            onSignOut={() => {
              clearToken();
              setToken("");
            }}
          />
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="infrastructure" element={<InfrastructurePage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="reliability" element={<ReliabilityPage role={session.data.role} />} />
        <Route path="settings" element={<SettingsPage role={session.data.role} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function Login({ error, onSubmit }: { error: unknown; onSubmit: (token: string) => void }) {
  const [value, setValue] = useState("");
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/api/v1/meta", {}, "") });
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="text-2xl font-semibold">CloudSentinel</h1>
      <p className="mt-2 text-sm text-muted">
        Enter a control-plane token. The dashboard does not embed credentials. Local development tokens are documented in the README.
      </p>
      <form
        className="mt-6 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(value.trim());
        }}
      >
        <Field label="Bearer token">
          <input
            className={inputClass}
            type="password"
            autoComplete="current-password"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            required
          />
        </Field>
        {error ? <ErrorText error={error} /> : null}
        <Button type="submit">Continue</Button>
      </form>
      {meta.data ? (
        <p className="mt-6 text-xs text-muted">
          Data plane: {meta.data.data_plane}. DNS failover: {meta.data.dns_failover ? "yes" : "no"}.
        </p>
      ) : null}
    </main>
  );
}
