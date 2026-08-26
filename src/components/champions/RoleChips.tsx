import { formatInitials } from "../format";
import { titleCase } from "./ChampionHeader";

export function RoleChips({
  roles,
  active,
  onSelect,
}: {
  roles: string[];
  active: string | null;
  onSelect: (role: string) => void;
}) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 8, overflowX: "auto", flex: "none" }}
      data-testid="role-chips"
    >
      {roles.map((r) => {
        const isActive = r === active;
        return (
          <button
            key={r}
            type="button"
            data-testid={`role-${r}`}
            onClick={() => onSelect(r)}
            style={{
              flex: "none",
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 12px 6px 6px",
              borderRadius: 999,
              border: "none",
              cursor: "pointer",
              background: isActive
                ? "linear-gradient(140deg,#3a3468,var(--color-surface-2) 80%)"
                : "var(--color-surface-2)",
              boxShadow: isActive
                ? "0 2px 0 rgba(0,0,0,.5),0 0 0 1.5px var(--color-accent)"
                : "var(--shadow-z1)",
            }}
          >
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: 8,
                display: "grid",
                placeItems: "center",
                font: "700 8px var(--font-mono)",
                background: isActive
                  ? "linear-gradient(150deg,var(--color-accent),var(--color-accent-low))"
                  : "linear-gradient(150deg,#4a5570,#232a3d)",
                color: isActive ? "var(--color-bg)" : "var(--color-soft-text)",
              }}
            >
              {formatInitials(r)}
            </span>
            <span
              className="mono-n"
              style={{
                fontSize: 11,
                fontWeight: isActive ? 600 : 400,
                color: isActive ? "#d2cefd" : "var(--color-dim)",
              }}
            >
              {titleCase(r)}
            </span>
          </button>
        );
      })}
      <span
        className="mono-n"
        style={{
          marginLeft: "auto",
          flex: "none",
          fontSize: 10,
          color: "var(--color-dimmer)",
          paddingRight: 4,
        }}
      >
        S/A/B/C tier from ≥100-game champions
      </span>
    </div>
  );
}
