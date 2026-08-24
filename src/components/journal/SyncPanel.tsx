import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useCancelSync, useSaveSettings, useSettings, useStartSync, useSyncStatus } from "../../api/hooks";
import { useEvents } from "../../api/sse";
import type { SseMessage } from "../../api/sse";
import type { SettingsPatch, SyncStatus } from "../../api/types";

const REGIONS = ["sea", "europe", "americas", "asia"] as const;
const DEFAULT_RIOT_ID = "SacredButtholio#OOF";

function isTerminal(state: SyncStatus["state"]): boolean {
  return state !== "running";
}

function FieldLabel({ children }: { children: string }) {
  return (
    <span
      style={{
        fontSize: 9,
        letterSpacing: ".08em",
        textTransform: "uppercase",
        color: "var(--color-dimmer)",
      }}
    >
      {children}
    </span>
  );
}

const inputStyle = {
  background: "var(--color-deep)",
} as const;

export function SyncPanel() {
  const settings = useSettings();
  const save = useSaveSettings();
  const start = useStartSync();
  const cancel = useCancelSync();
  const polled = useSyncStatus();

  const [live, setLive] = useState<SyncStatus | null>(null);
  useEvents((msg: SseMessage) => {
    if (msg.type === "sync.progress" || msg.type === "sync.done") {
      setLive(msg.data as SyncStatus);
    }
  });

  // polled status is the fallback baseline; SSE overlays fresher state
  useEffect(() => {
    if (!live && polled.data) setLive(polled.data);
  }, [polled.data, live]);

  const status = live ?? polled.data ?? null;
  const running = status?.state === "running";

  const [riotId, setRiotId] = useState(DEFAULT_RIOT_ID);
  const [region, setRegion] = useState<string>("sea");
  const [key, setKey] = useState("");
  const [autoSync, setAutoSync] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (settings.data && !dirty) {
      setRiotId(settings.data.riot_id ?? DEFAULT_RIOT_ID);
      setRegion(settings.data.region_route);
      setAutoSync(settings.data.auto_sync);
    }
  }, [settings.data, dirty]);

  function onSave(e: FormEvent) {
    e.preventDefault();
    const patch: SettingsPatch = {
      riot_id: riotId.trim() || null,
      region_route: region,
      auto_sync: autoSync,
    };
    if (key) patch.riot_key = key;
    save.mutate(patch, { onSuccess: () => setDirty(false) });
  }

  const total = status?.total_queued ?? 0;
  const doneCount = status?.downloaded ?? 0;
  const progressPct = total > 0 ? Math.min(100, Math.round((doneCount / total) * 100)) : 0;

  return (
    <section
      className="card3b"
      data-testid="sync-panel"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span className="kicker">SYNC · BACKFILL</span>
        <span
          className="mono-n"
          style={{ fontSize: 10, color: running ? "var(--color-accent)" : "var(--color-dimmer)" }}
        >
          {running ? "· running" : `· ${status?.state ?? "idle"}`}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Current-patch games download first; older history fills in across sessions.
      </p>

      <form onSubmit={onSave} className="grid grid-cols-2 gap-3" data-testid="sync-settings-form">
        <label className="flex flex-col gap-1">
          <FieldLabel>Riot ID</FieldLabel>
          <input
            value={riotId}
            onChange={(e) => {
              setRiotId(e.target.value);
              setDirty(true);
            }}
            data-testid="input-riot-id"
            style={inputStyle}
            className="rounded-[10px] border border-line bg-deep px-2.5 py-1.5 font-mono text-[11px] outline-none focus:border-accent"
          />
        </label>
        <label className="flex flex-col gap-1">
          <FieldLabel>Region route</FieldLabel>
          <select
            value={region}
            onChange={(e) => {
              setRegion(e.target.value);
              setDirty(true);
            }}
            data-testid="input-region"
            style={inputStyle}
            className="rounded-[10px] border border-line bg-deep px-2.5 py-1.5 text-[11px] outline-none focus:border-accent"
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <FieldLabel>Riot API key</FieldLabel>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={
              settings.data?.has_key ? "saved — leave blank to keep" : "paste a Riot API key"
            }
            data-testid="input-riot-key"
            style={inputStyle}
            className="rounded-[10px] border border-line bg-deep px-2.5 py-1.5 font-mono text-[11px] outline-none placeholder:text-dimmer focus:border-accent"
          />
        </label>
        <label className="mt-4 flex items-center gap-2 text-xs text-dim">
          <input
            type="checkbox"
            checked={autoSync}
            onChange={(e) => {
              setAutoSync(e.target.checked);
              setDirty(true);
            }}
            data-testid="input-auto-sync"
            className="size-3.5 accent-[#9184d9]"
          />
          Auto-sync when the app opens
        </label>
        <div className="col-span-2 flex items-center gap-3">
          <button
            type="submit"
            disabled={save.isPending}
            data-testid="save-settings"
            className="pill"
            style={{
              background: "var(--color-accent)",
              color: "#0e1020",
              border: "none",
              cursor: "pointer",
              opacity: save.isPending ? 0.4 : undefined,
              boxShadow: "0 3px 0 var(--color-accent-low),0 8px 16px -6px rgba(145,132,217,.6)",
            }}
          >
            Save settings
          </button>
          {save.isSuccess && !dirty && (
            <span data-testid="save-ok" className="mono-n text-xs text-teal">
              Saved.
            </span>
          )}
          {save.isError && (
            <span className="text-xs text-danger">Couldn't save — is the sidecar running?</span>
          )}
        </div>
      </form>

      <div style={{ borderTop: "1px solid var(--color-line)", paddingTop: 10 }}>
        <div className="flex items-center justify-between gap-3">
          <div
            style={{
              fontSize: 9,
              letterSpacing: ".08em",
              textTransform: "uppercase",
              color: "var(--color-dimmer)",
            }}
          >
            Backfill queue
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => start.mutate(undefined, { onSuccess: () => setLive(null) })}
              disabled={running || start.isPending}
              data-testid="start-sync"
              className="pill"
              style={{
                background: "var(--color-teal-low)",
                color: "var(--color-teal)",
                border: "none",
                cursor: "pointer",
                opacity: running || start.isPending ? 0.4 : undefined,
              }}
            >
              Start sync
            </button>
            <button
              type="button"
              onClick={() => cancel.mutate(undefined, { onSuccess: () => setLive(null) })}
              disabled={!running || cancel.isPending}
              data-testid="cancel-sync"
              className="pill"
              style={{
                background: "var(--color-surface-3)",
                color: "var(--color-dim)",
                border: "none",
                cursor: "pointer",
                opacity: !running || cancel.isPending ? 0.4 : undefined,
              }}
            >
              Cancel
            </button>
          </div>
        </div>

        {status && (
          <div className="mt-2" data-testid="sync-progress">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
              <div
                data-testid="sync-progress-bar"
                className={`h-full rounded-full ${isTerminal(status.state) ? "bg-teal" : "bg-accent"}`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-0.5 font-mono text-[10px] text-dim">
              <span data-testid="sync-counters">
                {doneCount} / {total} matches
                {status.skipped > 0 ? ` · ${status.skipped} skipped` : ""}
                {status.failed > 0 ? ` · ${status.failed} failed` : ""}
              </span>
              {status.current_match_id && (
                <span data-testid="sync-current" className="text-dimmer">
                  {status.current_match_id}
                </span>
              )}
              {cancel.isSuccess && status.state === "cancelled" && (
                <span className="text-amber">stopped — queue resumes next session</span>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
