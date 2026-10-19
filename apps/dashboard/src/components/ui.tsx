import type { ReactNode } from "react";

export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-md border border-line bg-panel">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold tracking-wide text-ink">{title}</h2>
        {action}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StatusPill({ value }: { value: string }) {
  const tone =
    value === "healthy" || value === "eligible" || value === "resolved" || value === "succeeded"
      ? "bg-good/15 text-good"
      : value === "degraded" || value === "open" || value === "running"
        ? "bg-warn/15 text-warn"
        : value === "unhealthy" || value === "failed" || value === "rejected"
          ? "bg-bad/15 text-bad"
          : "bg-line text-muted";
  return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${tone}`}>{value}</span>;
}

export function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 font-mono text-2xl text-ink">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </div>
  );
}

export function Banner({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-ink">{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function ErrorText({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "The request failed.";
  return (
    <p className="text-sm text-bad" role="alert">
      {message}
    </p>
  );
}

export function Loading() {
  return <p className="text-sm text-muted">Loading…</p>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-info";

export function Button({
  children,
  type = "button",
  disabled,
  onClick,
}: {
  children: ReactNode;
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className="rounded bg-info px-3 py-2 text-sm font-medium text-canvas disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}
