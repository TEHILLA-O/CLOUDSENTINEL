import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Empty, ErrorText, Loading, Metric, Panel, StatusPill } from "../components/ui";
import type { Environment, Incident, Meta, MetricsSummary, Page, Routing } from "../types";

export function OverviewPage() {
  const environments = useQuery({
    queryKey: ["environments"],
    queryFn: () => api<Page<Environment>>("/api/v1/environments"),
    refetchInterval: 5000,
  });
  const routing = useQuery({
    queryKey: ["routing"],
    queryFn: () => api<Routing>("/api/v1/routing/current"),
    refetchInterval: 5000,
  });
  const incidents = useQuery({
    queryKey: ["incidents"],
    queryFn: () => api<Page<Incident>>("/api/v1/incidents?limit=5"),
    refetchInterval: 5000,
  });
  const metrics = useQuery({
    queryKey: ["metrics"],
    queryFn: () => api<MetricsSummary>("/api/v1/metrics/summary"),
    refetchInterval: 5000,
  });
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/api/v1/meta", {}, "") });

  if (environments.isLoading || routing.isLoading || metrics.isLoading) {
    return <Loading />;
  }
  if (environments.error || routing.error || metrics.error) {
    return <ErrorText error={environments.error || routing.error || metrics.error} />;
  }
  const envs = environments.data?.items ?? [];
  const summary = metrics.data;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-muted">Live control-plane state. Numbers come from recorded probes and gateway samples.</p>
      </header>
      <div className="grid gap-3 md:grid-cols-4">
        <Metric label="Active route" value={routing.data?.active_environment_id ?? "none"} hint={routing.data?.reason} />
        <Metric label="Preferred" value={routing.data?.preferred_environment_id ?? "unset"} hint={routing.data?.mode} />
        <Metric
          label="Error rate"
          value={summary && summary.error_rate !== null ? `${(summary.error_rate * 100).toFixed(1)}%` : "n/a"}
          hint={summary ? `${summary.error_count}/${summary.request_count} gateway requests` : undefined}
        />
        <Metric
          label="Latency p50"
          value={summary?.latency_p50_ms !== null && summary?.latency_p50_ms !== undefined ? `${summary.latency_p50_ms} ms` : "n/a"}
          hint={summary?.latency_p95_ms !== null && summary?.latency_p95_ms !== undefined ? `p95 ${summary.latency_p95_ms} ms` : "No samples"}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Environments">
          {envs.length === 0 ? (
            <Empty>No environments are registered.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {envs.map((environment) => (
                <li key={environment.id} className="flex items-center justify-between py-3 text-sm">
                  <div>
                    <div className="font-medium">{environment.name}</div>
                    <div className="text-xs text-muted">
                      {environment.provider} · {environment.region} · {environment.role}
                    </div>
                  </div>
                  <StatusPill value={environment.state} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Recent incidents">
          {incidents.isLoading ? <Loading /> : null}
          {incidents.error ? <ErrorText error={incidents.error} /> : null}
          {!incidents.isLoading && !incidents.error && (incidents.data?.items.length ?? 0) === 0 ? (
            <Empty>No incidents recorded.</Empty>
          ) : null}
          {!incidents.isLoading && !incidents.error ? (
            <ul className="space-y-3 text-sm">
              {incidents.data?.items.map((incident) => (
                <li key={incident.id}>
                  <Link className="text-info" to={`/incidents/${incident.id}`}>
                    {incident.summary}
                  </Link>
                  <div className="mt-1 flex gap-2 text-xs text-muted">
                    <StatusPill value={incident.status} />
                    <span>{incident.trigger}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>
      </div>
      <Panel title="Gateway latency">
        {!summary || summary.series.length === 0 ? (
          <Empty>{summary?.measurement ?? "No measurements yet."}</Empty>
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={summary.series}>
                <CartesianGrid stroke="#2c3848" />
                <XAxis dataKey="minute" tick={{ fill: "#93a0b5", fontSize: 11 }} hide={summary.series.length > 8} />
                <YAxis tick={{ fill: "#93a0b5", fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="latency_p50_ms" stroke="#7eb6ff" dot={false} name="p50 ms" />
              </LineChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-muted">{summary.measurement}</p>
          </div>
        )}
      </Panel>
      <SampleRequest gatewayUrl={meta.data?.public_gateway_url ?? ""} />
    </div>
  );
}

function SampleRequest({ gatewayUrl }: { gatewayUrl: string }) {
  const [text, setText] = useState("The reliable cluster recovered after the failure.");
  const [result, setResult] = useState<string>("");
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${gatewayUrl}/api/v1/analyse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = (await response.json()) as { environment?: string; message?: string; summary?: string };
      if (!response.ok) {
        throw new Error(body.message || "The gateway rejected the request.");
      }
      return body;
    },
    onSuccess: async (body) => {
      setResult(`${body.environment ?? "unknown"}: ${body.summary ?? ""}`);
      await client.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
  return (
    <Panel title="Send a request through the gateway">
      {!gatewayUrl ? (
        <Empty>The public gateway URL is not available.</Empty>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            send.mutate();
          }}
        >
          <textarea
            className="min-h-24 w-full rounded border border-line bg-canvas px-3 py-2 text-sm"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" className="rounded bg-info px-3 py-2 text-sm font-medium text-canvas" disabled={send.isPending}>
            Analyse
          </button>
          <p className="text-xs text-muted">POST {gatewayUrl}/api/v1/analyse</p>
          {send.error ? <ErrorText error={send.error} /> : null}
          {result ? <p className="font-mono text-sm text-ink">{result}</p> : null}
        </form>
      )}
    </Panel>
  );
}
