import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Button, Empty, ErrorText, Field, Loading, Panel, inputClass } from "../components/ui";
import type { Environment, Page, Settings } from "../types";

export function SettingsPage({ role }: { role: string }) {
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<Settings>("/api/v1/settings") });
  const environments = useQuery({
    queryKey: ["environments"],
    queryFn: () => api<Page<Environment>>("/api/v1/environments"),
  });
  const [draft, setDraft] = useState<Settings | null>(null);
  const client = useQueryClient();
  useEffect(() => {
    if (settings.data) {
      setDraft(settings.data);
    }
  }, [settings.data]);
  const save = useMutation({
    mutationFn: (body: Settings) =>
      api<Settings>("/api/v1/settings", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: async (saved) => {
      setDraft(saved);
      await client.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  if (settings.isLoading || !draft) return <Loading />;
  if (settings.error) return <ErrorText error={settings.error} />;

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="text-sm text-muted">Values are validated by the control plane and stored in its database.</p>
      {role !== "admin" ? <Empty>The reader token cannot change settings.</Empty> : null}
      <Panel title="Thresholds">
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft) save.mutate(draft);
          }}
        >
          <NumberField label="Health-check interval (seconds)" value={draft.health_check_interval_seconds} onChange={(value) => update("health_check_interval_seconds", value)} />
          <NumberField label="Failure threshold" value={draft.failure_threshold} onChange={(value) => update("failure_threshold", value)} />
          <NumberField label="Success threshold" value={draft.success_threshold} onChange={(value) => update("success_threshold", value)} />
          <NumberField label="Cooldown (seconds)" value={draft.cooldown_seconds} onChange={(value) => update("cooldown_seconds", value)} />
          <NumberField label="Latency threshold (ms)" value={draft.latency_threshold_ms} onChange={(value) => update("latency_threshold_ms", value)} />
          <NumberField label="Latency breach threshold" value={draft.latency_breach_threshold} onChange={(value) => update("latency_breach_threshold", value)} />
          <NumberField label="Alert error rate (0-1)" value={draft.alert_error_rate} onChange={(value) => update("alert_error_rate", value)} />
          <NumberField label="Alert latency (ms)" value={draft.alert_latency_ms} onChange={(value) => update("alert_latency_ms", value)} />
          <Field label="Preferred environment">
            <select
              className={inputClass}
              value={draft.preferred_environment_id ?? ""}
              onChange={(event) => update("preferred_environment_id", event.target.value)}
            >
              {(environments.data?.items ?? []).map((environment) => (
                <option key={environment.id} value={environment.id}>
                  {environment.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Recovery policy">
            <select className={inputClass} value={draft.recovery_policy} onChange={(event) => update("recovery_policy", event.target.value)}>
              <option value="automatic">automatic</option>
              <option value="manual">manual</option>
            </select>
          </Field>
          <div className="md:col-span-2">
            <Button type="submit" disabled={role !== "admin" || save.isPending}>
              Save settings
            </Button>
          </div>
        </form>
        {save.error ? <div className="mt-3"><ErrorText error={formatError(save.error)} /></div> : null}
        {save.isSuccess ? <p className="mt-3 text-sm text-good">Saved.</p> : null}
      </Panel>
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <Field label={label}>
      <input className={inputClass} type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </Field>
  );
}

function formatError(error: unknown): Error {
  if (error instanceof ApiError) {
    const details = error.body.details?.map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ");
    return new Error(details || error.message);
  }
  return error instanceof Error ? error : new Error("Save failed.");
}
