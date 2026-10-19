import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../api";
import { Banner, Button, Empty, ErrorText, Field, Loading, Panel, inputClass } from "../components/ui";
import type { Environment, Experiment, Page } from "../types";

const KINDS = [
  ["inject_errors", "Simulate API errors"],
  ["inject_latency", "Introduce response latency"],
  ["fail_readiness", "Fail the readiness probe"],
  ["fail_liveness", "Fail the liveness probe"],
  ["clear_faults", "Clear injected faults"],
  ["restart_local_pods", "Restart an approved local deployment"],
] as const;

export function ReliabilityPage({ role }: { role: string }) {
  const environments = useQuery({
    queryKey: ["environments"],
    queryFn: () => api<Page<Environment>>("/api/v1/environments"),
  });
  const [kind, setKind] = useState<string>(KINDS[0][0]);
  const [target, setTarget] = useState("azure-dev");
  const [duration, setDuration] = useState(60);
  const [latency, setLatency] = useState(1200);
  const [result, setResult] = useState<Experiment | null>(null);
  const client = useQueryClient();
  const approved = (environments.data?.items ?? []).filter((item) => item.experiments_allowed);
  const run = useMutation({
    mutationFn: () =>
      api<Experiment>("/api/v1/experiments", {
        method: "POST",
        body: JSON.stringify({
          kind,
          target_environment_id: target,
          duration_seconds: duration,
          latency_ms: latency,
          error_status: 500,
        }),
      }),
    onSuccess: async (experiment) => {
      setResult(experiment);
      await client.invalidateQueries({ queryKey: ["routing"] });
      await client.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Reliability testing</h1>
      <Banner>
        Experiments call a fixed fault API or, when explicitly enabled, one preconfigured kubectl rollout restart. The dashboard cannot run arbitrary commands. Cloud runtimes are rejected.
      </Banner>
      {environments.isLoading ? <Loading /> : null}
      {environments.error ? <ErrorText error={environments.error} /> : null}
      {role !== "admin" ? <Empty>The reader token can view this page. Starting an experiment requires the admin token.</Empty> : null}
      <Panel title="Approved experiment">
        {approved.length === 0 ? <Empty>No environment is approved for experiments.</Empty> : null}
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            run.mutate();
          }}
        >
          <Field label="Experiment">
            <select className={inputClass} value={kind} onChange={(event) => setKind(event.target.value)}>
              {KINDS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Target">
            <select className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)}>
              {approved.map((environment) => (
                <option key={environment.id} value={environment.id}>
                  {environment.name} ({environment.runtime})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Duration seconds">
            <input className={inputClass} type="number" min={1} max={300} value={duration} onChange={(event) => setDuration(Number(event.target.value))} />
          </Field>
          <Field label="Latency ms">
            <input className={inputClass} type="number" min={0} max={10000} value={latency} onChange={(event) => setLatency(Number(event.target.value))} />
          </Field>
          <div className="md:col-span-2">
            <Button type="submit" disabled={role !== "admin" || run.isPending || approved.length === 0}>
              Run experiment
            </Button>
          </div>
        </form>
        {run.error ? <div className="mt-3"><ErrorText error={formatError(run.error)} /></div> : null}
        {result ? (
          <pre className="mt-4 overflow-auto rounded bg-canvas p-3 text-xs text-ink">{JSON.stringify(result, null, 2)}</pre>
        ) : null}
      </Panel>
    </div>
  );
}

function formatError(error: unknown): Error {
  if (error instanceof ApiError && error.body.details?.length) {
    return new Error(error.body.details.map((item) => item.msg).join(" "));
  }
  return error instanceof Error ? error : new Error("Experiment failed.");
}
