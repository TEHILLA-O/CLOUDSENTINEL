import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Loading, Panel, StatusPill } from "../components/ui";
import type { Incident } from "../types";

export function IncidentDetailPage() {
  const { incidentId } = useParams();
  const incident = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => api<Incident>(`/api/v1/incidents/${incidentId}`),
    enabled: Boolean(incidentId),
    refetchInterval: 5000,
  });
  if (incident.isLoading) return <Loading />;
  if (incident.error) return <ErrorText error={incident.error} />;
  if (!incident.data) return null;
  const item = incident.data;
  return (
    <div className="space-y-4">
      <Link className="text-sm text-info" to="/incidents">
        Back to incidents
      </Link>
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Incident</h1>
        <StatusPill value={item.status} />
      </div>
      <p className="text-sm text-ink">{item.summary}</p>
      <dl className="grid gap-3 text-sm md:grid-cols-3">
        <Fact label="Started" value={item.started_at} />
        <Fact label="Detected" value={item.detected_at} />
        <Fact label="Routing changed" value={item.routing_changed_at ?? "not changed"} />
        <Fact label="Resolved" value={item.resolved_at ?? "open"} />
        <Fact label="Duration" value={item.duration_seconds !== null ? `${item.duration_seconds}s` : "n/a"} />
        <Fact label="Detection" value={item.detection_seconds !== null ? `${item.detection_seconds}s` : "n/a"} />
        <Fact label="From" value={item.from_environment_id ?? "n/a"} />
        <Fact label="To" value={item.to_environment_id ?? "n/a"} />
        <Fact label="Trigger" value={item.trigger} />
      </dl>
      <Panel title="Timeline">
        {item.events.length === 0 ? <p className="text-sm text-muted">No events were stored.</p> : null}
        <ol className="space-y-4">
          {item.events.map((event) => (
            <li key={event.id} className="border-l border-line pl-4">
              <div className="text-xs uppercase text-muted">
                {event.kind} · {event.occurred_at}
              </div>
              <p className="mt-1 text-sm">{event.message}</p>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-panel px-3 py-2">
      <dt className="text-xs uppercase text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-xs text-ink">{value}</dd>
    </div>
  );
}
