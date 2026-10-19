import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Empty, ErrorText, Loading, Panel, StatusPill } from "../components/ui";
import type { Environment, Page } from "../types";

export function InfrastructurePage() {
  const environments = useQuery({
    queryKey: ["environments"],
    queryFn: () => api<Page<Environment>>("/api/v1/environments"),
    refetchInterval: 5000,
  });
  if (environments.isLoading) return <Loading />;
  if (environments.error) return <ErrorText error={environments.error} />;
  const items = environments.data?.items ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Infrastructure</h1>
      <p className="text-sm text-muted">
        Cluster inventory is shown only when the control plane has it. A null Kubernetes version means the cluster API is not connected.
      </p>
      {items.length === 0 ? <Empty>No environments are registered.</Empty> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((environment) => (
          <Panel key={environment.id} title={environment.name}>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Item label="Provider" value={environment.provider} />
              <Item label="Region" value={environment.region} />
              <Item label="Cluster" value={environment.cluster_name} />
              <Item label="Kubernetes" value={environment.kubernetes_version ?? "not reported"} />
              <Item label="Runtime" value={environment.runtime} />
              <Item label="Verification" value={environment.verification} />
              <Item label="Role" value={environment.role} />
              <div>
                <dt className="text-xs uppercase text-muted">Health</dt>
                <dd className="mt-1">
                  <StatusPill value={environment.state} />
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-xs text-muted">{environment.notes}</p>
            <p className="mt-2 text-xs text-muted">
              Last probe: {environment.last_outcome ?? "none"}
              {environment.last_latency_ms !== null ? ` · ${environment.last_latency_ms} ms` : ""}
              {environment.last_detail ? ` · ${environment.last_detail}` : ""}
            </p>
            <p className="mt-2 text-xs text-muted">
              Node and pod counts are not shown because this console is not connected to a Kubernetes API.
            </p>
          </Panel>
        ))}
      </div>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-ink">{value}</dd>
    </div>
  );
}
