import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorText, Loading, StatusPill } from "../components/ui";
import type { Incident, Page } from "../types";

export function IncidentsPage() {
  const incidents = useQuery({
    queryKey: ["incidents", "all"],
    queryFn: () => api<Page<Incident>>("/api/v1/incidents?limit=50"),
    refetchInterval: 5000,
  });
  if (incidents.isLoading) return <Loading />;
  if (incidents.error) return <ErrorText error={incidents.error} />;
  const items = incidents.data?.items ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incidents</h1>
      {items.length === 0 ? <Empty>No incidents recorded.</Empty> : null}
      <ul className="divide-y divide-line rounded-md border border-line bg-panel">
        {items.map((incident) => (
          <li key={incident.id} className="px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <Link className="text-sm text-info" to={`/incidents/${incident.id}`}>
                {incident.summary}
              </Link>
              <StatusPill value={incident.status} />
            </div>
            <p className="mt-1 text-xs text-muted">
              {incident.started_at} · trigger {incident.trigger}
              {incident.duration_seconds !== null ? ` · ${incident.duration_seconds}s open` : ""}
              {incident.detection_seconds !== null ? ` · detection ${incident.detection_seconds}s` : ""}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
