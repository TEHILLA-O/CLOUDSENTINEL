import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Empty, ErrorText, Loading, Panel, StatusPill } from "../components/ui";
import type { Observation, Page, Service } from "../types";

export function ServicesPage() {
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api<Page<Service>>("/api/v1/services"),
    refetchInterval: 5000,
  });
  if (services.isLoading) return <Loading />;
  if (services.error) return <ErrorText error={services.error} />;
  const items = services.data?.items ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Services</h1>
      {items.length === 0 ? <Empty>No services are registered.</Empty> : null}
      {items.map((service) => (
        <ServiceCard key={service.id} service={service} />
      ))}
    </div>
  );
}

function ServiceCard({ service }: { service: Service }) {
  const health = useQuery({
    queryKey: ["service-health", service.id],
    queryFn: () => api<Page<Observation>>(`/api/v1/services/${service.id}/health?limit=8`),
    refetchInterval: 5000,
  });
  return (
    <Panel title={`${service.name} · ${service.environment_id}`}>
      <p className="text-sm text-muted">
        {service.base_url}
        {service.analyse_path}
      </p>
      <div className="mt-2">
        <StatusPill value={service.state} />
      </div>
      {health.isLoading ? <Loading /> : null}
      {health.error ? <ErrorText error={health.error} /> : null}
      {health.data && health.data.items.length === 0 ? <Empty>No health observations yet.</Empty> : null}
      {health.data && health.data.items.length > 0 ? (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted">
            <tr>
              <th className="py-2">Time</th>
              <th>Outcome</th>
              <th>Latency</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {health.data.items.map((row) => (
              <tr key={row.id} className="border-t border-line">
                <td className="py-2 font-mono text-xs">{row.checked_at}</td>
                <td>{row.outcome}</td>
                <td>{row.latency_ms} ms</td>
                <td className="text-muted">{row.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </Panel>
  );
}
