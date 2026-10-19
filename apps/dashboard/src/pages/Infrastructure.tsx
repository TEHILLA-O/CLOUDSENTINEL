import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Empty, ErrorText, Loading, Panel, StatusPill } from "../components/ui";
import type { ClusterInventory, Environment, Page } from "../types";

export function InfrastructurePage() {
  const environments = useQuery({
    queryKey: ["environments"],
    queryFn: () => api<Page<Environment>>("/api/v1/environments"),
    refetchInterval: 5000,
  });
  const cluster = useQuery({
    queryKey: ["cluster"],
    queryFn: () => api<ClusterInventory>("/api/v1/cluster"),
    refetchInterval: 5000,
  });
  if (environments.isLoading) return <Loading />;
  if (environments.error) return <ErrorText error={environments.error} />;
  const items = environments.data?.items ?? [];
  const inventory = cluster.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Infrastructure</h1>
      {cluster.isLoading ? <Loading /> : null}
      {cluster.error ? <ErrorText error={cluster.error} /> : null}
      {inventory ? (
        <Panel title={inventory.cluster_name || "Cluster"}>
          {inventory.available ? (
            <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <Item label="Kubernetes" value={inventory.kubernetes_version ?? "not reported"} />
              <Item label="Nodes ready" value={`${inventory.ready_node_count}/${inventory.node_count}`} />
              <Item label="Pods" value={String(inventory.pods.length)} />
              <Item label="Ready pods" value={String(inventory.pods.filter((pod) => pod.ready).length)} />
            </dl>
          ) : (
            <p className="text-sm text-muted">{inventory.detail ?? "The cluster API did not respond."}</p>
          )}
        </Panel>
      ) : null}
      {items.length === 0 ? <Empty>No environments are registered.</Empty> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((environment) => {
          const pods = (inventory?.pods ?? []).filter((pod) => pod.app === deploymentName(environment.id));
          return (
            <Panel key={environment.id} title={environment.name}>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Item label="Provider" value={environment.provider} />
                <Item label="Region" value={environment.region} />
                <Item label="Cluster" value={environment.cluster_name} />
                <Item label="Runtime" value={environment.runtime} />
                <Item label="Service" value={environment.id} />
                <Item label="Endpoint" value={environment.base_url} />
                <div>
                  <dt className="text-xs uppercase text-muted">Health</dt>
                  <dd className="mt-1">
                    <StatusPill value={environment.state} />
                  </dd>
                </div>
                <Item label="Probe" value={environment.verification} />
              </dl>
              <p className="mt-4 text-xs text-muted">
                Last probe: {environment.last_outcome ?? "none"}
                {environment.last_latency_ms !== null ? ` · ${environment.last_latency_ms} ms` : ""}
                {environment.last_detail ? ` · ${environment.last_detail}` : ""}
              </p>
              {pods.length > 0 ? (
                <ul className="mt-3 space-y-1 text-xs text-muted">
                  {pods.map((pod) => (
                    <li key={pod.name}>
                      {pod.name} · {pod.phase} · {pod.ready ? "ready" : "not ready"} · {pod.node ?? "unscheduled"}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Panel>
          );
        })}
      </div>
    </div>
  );
}

function deploymentName(environmentId: string): string {
  if (environmentId === "azure-dev") return "analysis-azure";
  if (environmentId === "gcp-dev") return "analysis-gcp";
  return environmentId;
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase text-muted">{label}</dt>
      <dd className="mt-1 break-all font-mono text-ink">{value}</dd>
    </div>
  );
}
