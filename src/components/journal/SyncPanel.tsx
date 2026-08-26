import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { actionableErrorMessage } from "../../api/client";
import { useCancelSync, useSaveSettings, useSettings, useStartSync, useSyncStatus } from "../../api/hooks";
import { useEvents } from "../../api/sse";
import type { SseMessage } from "../../api/sse";
import type { RegionRoute, SettingsPatch, SyncStatus } from "../../api/types";
import { isValidRiotId } from "./identity";

function isSyncStatus(value: unknown): value is SyncStatus {
  if (typeof value !== "object" || value === null) return false;
  if (
    !("state" in value) ||
    !("mode" in value) ||
    !("total_queued" in value) ||
    !("downloaded" in value) ||
    !("skipped" in value) ||
    !("failed" in value) ||
    !("current_match_id" in value) ||
    !("started_at" in value)
  ) {
    return false;
  }
  return (
    (value.state === "idle" ||
      value.state === "running" ||
      value.state === "cancelled" ||
      value.state === "error") &&
    (value.mode === "era_first" || value.mode === "import") &&
    typeof value.total_queued === "number" &&
    typeof value.downloaded === "number" &&
    typeof value.skipped === "number" &&
    typeof value.failed === "number" &&
    (typeof value.current_match_id === "string" || value.current_match_id === null) &&
    (typeof value.started_at === "string" || value.started_at === null)
  );
}
const REGIONS: readonly RegionRoute[] = ["sea", "europe", "americas", "asia"];
const DEFAULT_RIOT_ID = "";

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

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
    if (
      (msg.type === "sync.progress" || msg.type === "sync.done") &&
      isSyncStatus(msg.data)
    ) {
      setLive(msg.data);
    }
  });

  // polled status is the fallback baseline; SSE overlays fresher state
  useEffect(() => {
    if (!live && polled.data) setLive(polled.data);
  }, [polled.data, live]);
  const status = live ?? polled.data ?? null;
  const running = status?.state === "running";

  const [riotId, setRiotId] = useState(DEFAULT_RIOT_ID);
  const [region, setRegion] = useState<RegionRoute>("sea");
  const [key, setKey] = useState("");
  const [autoSync, setAutoSync] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [riotIdEdited, setRiotIdEdited] = useState(false);
  const [regionEdited, setRegionEdited] = useState(false);
  const [autoSyncEdited, setAutoSyncEdited] = useState(false);
  const [riotIdTouched, setRiotIdTouched] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const riotIdValid = isValidRiotId(riotId);
  const showRiotIdError = !riotIdValid && (riotIdTouched || attempted);

  useEffect(() => {
    if (settings.data) {
      if (!riotIdEdited) setRiotId(settings.data.riot_id ?? DEFAULT_RIOT_ID);
      if (!regionEdited) setRegion(settings.data.region_route);
      if (!autoSyncEdited) setAutoSync(settings.data.auto_sync);
    }
  }, [settings.data, riotIdEdited, regionEdited, autoSyncEdited]);

  function onSave(e: FormEvent) {
    e.preventDefault();
    setAttempted(true);
    setRiotIdTouched(true);
    if (!riotIdValid) return;

    const patch: SettingsPatch = {
      riot_id: riotId.trim() || null,
      region_route: region,
      auto_sync: autoSync,
    };
    if (key) patch.riot_key = key;
    save.mutate(patch, {
      onSuccess: () => {
        setDirty(false);
        setRiotIdEdited(false);
        setRegionEdited(false);
        setAutoSyncEdited(false);
      },
    });
  }

  const requestPending = save.isPending || start.isPending || cancel.isPending;
  const startDisabledReason = running
    ? "Backfill is running."
    : requestPending
      ? "Loading…"
      : !riotIdValid
        ? "Enter a valid Riot ID before starting Backfill."
        : dirty
          ? "Save settings before starting Backfill."
          : !settings.data
            ? settings.isError
              ? "Unavailable: saved settings could not be loaded."
              : "Waiting for saved settings"
            : !settings.data.riot_id
              ? "Save a Riot ID before starting Backfill."
              : null;
  const startDisabled = startDisabledReason !== null;
  const sourceCopy = requestPending
    ? "Loading…"
    : polled.isPending && !status
      ? "Loading…"
      : polled.isError && !status
        ? "Unavailable: Backfill status could not be loaded."
        : !status
          ? "Waiting for Backfill status"
          : null;

  function onStart() {
    setAttempted(true);
    setRiotIdTouched(true);
    if (startDisabled) return;
    start.mutate(undefined, { onSuccess: (next) => setLive(next) });
  }
  const total = status?.total_queued ?? 0;
  const doneCount = status?.downloaded ?? 0;
  const progressPct = total > 0 ? Math.min(100, Math.round((doneCount / total) * 100)) : 0;

  return (
    <section
      className="card3b"
      data-testid="sync-panel"
      aria-label="Backfill"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span
          className="mono-n"
          style={{ fontSize: 10, color: running ? "var(--color-accent)" : "var(--color-dimmer)" }}
        >
          {running ? "· running" : `· ${status?.state ?? "idle"}`}
        </span>
        {sourceCopy && (
          <span
            data-testid="backfill-source-status"
            role="status"
            aria-live="polite"
            style={{ fontSize: 10, color: "var(--color-dimmer)" }}
          >
            {sourceCopy}
          </span>
        )}
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
              setRiotIdEdited(true);
              setDirty(true);
            }}
            onBlur={() => setRiotIdTouched(true)}
            data-testid="input-riot-id"
            aria-invalid={showRiotIdError}
            aria-describedby={showRiotIdError ? "riot-id-error" : undefined}
            style={inputStyle}
            className="rounded-[10px] border border-line bg-deep px-2.5 py-1.5 font-mono text-[11px] outline-none focus:border-accent"
          />
          {showRiotIdError && (
            <span id="riot-id-error" data-testid="riot-id-error" className="text-[10px] text-amber">
              Enter a valid GameName#TAG before starting Backfill.
            </span>
          )}
        </label>
        <label className="flex flex-col gap-1">
          <FieldLabel>Region route</FieldLabel>
          <select
            value={region}
            onChange={(e) => {
              setRegion(e.target.value as RegionRoute);
              setRegionEdited(true);
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
            onChange={(e) => {
              setKey(e.target.value);
              setDirty(true);
            }}
            placeholder={
              settings.data?.has_key ? "saved — leave blank to keep" : "paste a Riot API key"
            }
            data-testid="input-riot-key"
            style={inputStyle}
            className="rounded-[10px] border border-line bg-deep px-2.5 py-1.5 font-mono text-[11px] outline-none placeholder:text-dimmer focus:border-accent"
          />
        </label>
        {autoSync && settings.data && !settings.data.has_key && (
          <span
            data-testid="auto-sync-prerequisite"
            className="col-span-2 text-[10px] text-amber"
          >
            Save a Riot API key to enable auto-sync when the app opens.
          </span>
        )}
        <label className="mt-4 flex min-h-[24px] items-center gap-2 text-xs text-dim">
          <input
            type="checkbox"
            checked={autoSync}
            onChange={(e) => {
              setAutoSync(e.target.checked);
              setAutoSyncEdited(true);
              setDirty(true);
            }}
            data-testid="input-auto-sync"
            className="bl-check"
          />
          Auto-sync when the app opens
        </label>
        <div className="col-span-2 flex items-center gap-3">
          <button
            type="submit"
            disabled={save.isPending}
            aria-busy={save.isPending}
            data-testid="save-settings"
            className="pill"
            style={{
              background: "var(--color-surface-2)",
              color: "var(--color-dim)",
              border: "1px solid var(--color-line)",
              cursor: save.isPending ? "default" : "pointer",
              opacity: save.isPending ? 0.4 : undefined,
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
            <span data-testid="save-error" role="alert" className="text-xs text-danger">
              {actionableErrorMessage(save.error, "sync")}
            </span>
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
              onClick={onStart}
              disabled={startDisabled}
              aria-describedby={startDisabled ? "start-disabled-reason" : undefined}
              aria-busy={start.isPending}
              data-testid="start-sync"
              className="pill"
              style={{
                background: "var(--color-accent)",
                color: "#0e1020",
                border: "none",
                cursor: startDisabled ? "default" : "pointer",
                opacity: startDisabled ? 0.4 : undefined,
                boxShadow: "0 3px 0 var(--color-accent-low),0 8px 16px -6px rgba(145,132,217,.6)",
              }}
            >
              Start Backfill
            </button>
            <button
              type="button"
              onClick={() => cancel.mutate(undefined, { onSuccess: (next) => setLive(next) })}
              disabled={!running || cancel.isPending}
              data-testid="cancel-sync"
              className="pill"
              style={{
                background: "transparent",
                color: "var(--color-dim)",
                border: "1px solid var(--color-line)",
                cursor: !running || cancel.isPending ? "default" : "pointer",
                opacity: !running || cancel.isPending ? 0.4 : undefined,
              }}
            >
              Cancel
            </button>
          </div>
        </div>
        {startDisabledReason && (
          <p
            id="start-disabled-reason"
            data-testid="start-disabled-reason"
            role="status"
            style={{ margin: "6px 0 0", fontSize: 10, color: "var(--color-dimmer)" }}
          >
            {startDisabledReason}
          </p>
        )}
        {start.isError && (
          <p data-testid="start-error" role="alert" style={{ margin: "6px 0 0", fontSize: 10, color: "var(--color-danger)" }}>
            {actionableErrorMessage(start.error, "sync")}
          </p>
        )}
        {cancel.isError && (
          <p data-testid="cancel-error" role="alert" style={{ margin: "6px 0 0", fontSize: 10, color: "var(--color-danger)" }}>
            {actionableErrorMessage(cancel.error, "sync")}
          </p>
        )}

        {status && (
          <div className="mt-2" data-testid="sync-progress">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
              <div
                data-testid="sync-progress-bar"
                className={`bl-width h-full rounded-full ${isTerminal(status.state) ? "bg-teal" : "bg-accent"}`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-0.5 font-mono text-[10px] text-dim">
              <span data-testid="sync-counters">
                {formatCount(doneCount)} / {formatCount(total)} matches
                {status.skipped > 0 ? ` · ${formatCount(status.skipped)} skipped` : ""}
                {status.failed > 0 ? ` · ${formatCount(status.failed)} failed` : ""}
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
            {status.state === "error" && (
              <p data-testid="sync-status-error" role="alert" className="mt-1 text-[10px] text-danger">
                Unavailable: Backfill stopped before completion; check settings and try again.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
