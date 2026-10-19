import { NavLink, Outlet } from "react-router-dom";
import { clearToken } from "../api";

const links = [
  ["/", "Overview"],
  ["/infrastructure", "Infrastructure"],
  ["/services", "Services"],
  ["/incidents", "Incidents"],
  ["/reliability", "Reliability"],
  ["/settings", "Settings"],
] as const;

export function Layout({ role, onSignOut }: { role: string; onSignOut: () => void }) {
  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="border-b border-line bg-panel md:border-b-0 md:border-r">
        <div className="px-4 py-5">
          <div className="text-xs uppercase tracking-[0.2em] text-muted">CloudSentinel</div>
          <div className="mt-1 text-sm text-ink">Reliability console</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-3 md:block md:px-2" aria-label="Primary">
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `block whitespace-nowrap rounded px-3 py-2 text-sm ${isActive ? "bg-canvas text-ink" : "text-muted hover:text-ink"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden px-4 py-4 text-xs text-muted md:block">
          Signed in as <span className="text-ink">{role}</span>
          <button
            type="button"
            className="mt-3 block text-info"
            onClick={() => {
              clearToken();
              onSignOut();
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="px-4 py-6 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}
