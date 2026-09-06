import { useCallback, useEffect, useRef, useState } from "react";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type DownloadEvent, type Update } from "@tauri-apps/plugin-updater";

export type UpdaterState =
  | { status: "current" }
  | { status: "available"; version: string }
  | { status: "downloading"; version: string; progress: number | null }
  | { status: "ready-to-restart"; version: string }
  | { status: "failed"; message: string };

export type UpdaterRuntime = {
  check: () => Promise<Pick<Update, "version" | "downloadAndInstall"> | null>;
  relaunch: () => Promise<void>;
};

const tauriRuntime: UpdaterRuntime = { check, relaunch };

export function updaterStateForCheck(
  update: Pick<Update, "version"> | null,
): Extract<UpdaterState, { status: "current" | "available" }> {
  return update ? { status: "available", version: update.version } : { status: "current" };
}

export function updaterStateForDownload(
  version: string,
  progress: number | null,
): Extract<UpdaterState, { status: "downloading" }> {
  return { status: "downloading", version, progress };
}
export function updaterStateForReady(
  version: string,
): Extract<UpdaterState, { status: "ready-to-restart" }> {
  return { status: "ready-to-restart", version };
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "";
}

export function updaterStateForError(error: unknown): Extract<UpdaterState, { status: "failed" }> {
  const detail = errorText(error).toLowerCase();
  let message =
    "The update could not be installed. Your current install is still runnable; try again later.";

  if (detail.includes("signature") || detail.includes("public key")) {
    message =
      "The release signature could not be verified. Your current install is still runnable; try again later.";
  } else if (
    detail.includes("version") ||
    detail.includes("downgrade") ||
    detail.includes("older")
  ) {
    message =
      "The release version is not compatible with this install. Your current install is still runnable; try again later.";
  } else if (
    detail.includes("platform") ||
    detail.includes("architecture") ||
    detail.includes("target")
  ) {
    message =
      "This release is not available for this platform or architecture. Your current install is still runnable; try again later.";
  } else if (
    detail.includes("json") ||
    detail.includes("metadata") ||
    detail.includes("manifest") ||
    detail.includes("parse")
  ) {
    message =
      "The release metadata is malformed. Your current install is still runnable; try again later.";
  } else if (
    detail.includes("network") ||
    detail.includes("timeout") ||
    detail.includes("connect") ||
    detail.includes("fetch") ||
    detail.includes("http")
  ) {
    message =
      "The update check could not reach the release server. Your current install is still runnable; try again later.";
  } else if (
    detail.includes("download") ||
    detail.includes("interrupted") ||
    detail.includes("aborted")
  ) {
    message =
      "The update download was interrupted. Your current install is still runnable; try again later.";
  }

  return { status: "failed", message };
}

function statusText(state: UpdaterState): string {
  switch (state.status) {
    case "current":
      return "Bhayanak Legends is up to date.";
    case "available":
      return `Version ${state.version} is available.`;
    case "downloading":
      return state.progress === null
        ? `Downloading version ${state.version}…`
        : `Downloading version ${state.version}… ${state.progress}%`;
    case "ready-to-restart":
      return `Version ${state.version} is ready to restart.`;
    case "failed":
      return `Update unavailable. ${state.message}`;
  }
}
export function UpdaterStatus({ runtime = tauriRuntime }: { runtime?: UpdaterRuntime }) {
  const [state, setState] = useState<UpdaterState>({ status: "current" });
  const update = useRef<Pick<Update, "version" | "downloadAndInstall"> | null>(null);
  const mounted = useRef(true);
  const nativeRuntime =
    runtime !== tauriRuntime ||
    (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window);

  const checkForUpdate = useCallback(async () => {
    try {
      const candidate = await runtime.check();
      if (!mounted.current) return;
      update.current = candidate;
      setState(updaterStateForCheck(candidate));
    } catch (error) {
      if (mounted.current) setState(updaterStateForError(error));
    }
  }, [runtime]);

  useEffect(() => {
    if (!nativeRuntime) return;
    mounted.current = true;
    void checkForUpdate();
    return () => {
      mounted.current = false;
      update.current = null;
    };
  }, [checkForUpdate, nativeRuntime]);

  const installUpdate = async () => {
    const candidate = update.current;
    if (!candidate) return;

    let downloadedBytes = 0;
    let contentLength: number | undefined;
    setState(updaterStateForDownload(candidate.version, null));
    try {
      await candidate.downloadAndInstall((event: DownloadEvent) => {
        if (event.event === "Started") {
          downloadedBytes = 0;
          contentLength = event.data.contentLength;
        } else if (event.event === "Progress") {
          downloadedBytes += event.data.chunkLength;
          const progress = contentLength
            ? Math.min(100, Math.round((downloadedBytes / contentLength) * 100))
            : null;
          if (mounted.current) setState(updaterStateForDownload(candidate.version, progress));
        }
      });
      if (mounted.current) setState(updaterStateForReady(candidate.version));
    } catch (error) {
      if (mounted.current) setState(updaterStateForError(error));
    }
  };

  const restartApp = async () => {
    try {
      await runtime.relaunch();
    } catch (error) {
      if (mounted.current) setState(updaterStateForError(error));
    }
  };

  if (!nativeRuntime) return null;
  return (
    <section
      className="pill"
      aria-label="Application updates"
      aria-live="polite"
      data-testid="updater-status"
      style={{
        maxWidth: 460,
        color: "var(--color-dim)",
        background: "var(--color-surface-2)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <span>{statusText(state)}</span>
      {state.status === "available" && (
        <button
          type="button"
          onClick={() => void installUpdate()}
          style={{
            border: 0,
            borderRadius: 999,
            padding: "3px 8px",
            color: "var(--color-bg)",
            background: "var(--color-accent)",
            font: "600 10px var(--font-mono)",
          }}
        >
          Install update
        </button>
      )}
      {state.status === "ready-to-restart" && (
        <button
          type="button"
          onClick={() => void restartApp()}
          style={{
            border: 0,
            borderRadius: 999,
            padding: "3px 8px",
            color: "var(--color-bg)",
            background: "var(--color-teal)",
            font: "600 10px var(--font-mono)",
          }}
        >
          Restart app
        </button>
      )}
      {state.status === "failed" && (
        <button
          type="button"
          onClick={() => void checkForUpdate()}
          style={{
            border: 0,
            borderRadius: 999,
            padding: "3px 8px",
            color: "var(--color-bg)",
            background: "var(--color-amber)",
            font: "600 10px var(--font-mono)",
          }}
        >
          Try again
        </button>
      )}
    </section>
  );
}
