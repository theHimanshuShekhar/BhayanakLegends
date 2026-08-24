import { describe, expect, it } from "vitest";
import {
  updaterStateForCheck,
  updaterStateForError,
  updaterStateForDownload,
  updaterStateForReady,
  type UpdaterState,
} from "./UpdaterStatus";

describe("updater state transitions", () => {
  it("represents no update and an available version with typed states", () => {
    expect(updaterStateForCheck(null)).toEqual<UpdaterState>({ status: "current" });
    expect(updaterStateForCheck({ version: "0.2.0" })).toEqual<UpdaterState>({
      status: "available",
      version: "0.2.0",
    });
  });

  it("keeps download progress separate from the restart-ready state", () => {
    expect(updaterStateForDownload("0.2.0", 42)).toEqual<UpdaterState>({
      status: "downloading",
      version: "0.2.0",
      progress: 42,
    });
    expect(updaterStateForDownload("0.2.0", null)).toEqual<UpdaterState>({
      status: "downloading",
      version: "0.2.0",
      progress: null,
    });
    expect(updaterStateForReady("0.2.0")).toEqual<UpdaterState>({
      status: "ready-to-restart",
      version: "0.2.0",
    });
  });

  it("turns updater failure categories into safe, actionable copy", () => {
    expect(updaterStateForError(new Error("signature verification failed")).status).toBe("failed");
    expect(updaterStateForError(new Error("signature verification failed")).message).toMatch(
      /signature.*verified/i,
    );
    expect(updaterStateForError(new Error("unsupported target architecture")).message).toMatch(
      /platform or architecture/i,
    );
    expect(updaterStateForError(new Error("malformed JSON metadata")).message).toMatch(
      /metadata is malformed/i,
    );
    expect(updaterStateForError(new Error("version is older than current install")).message).toMatch(
      /version is not compatible/i,
    );
    expect(updaterStateForError(new Error("download interrupted")).message).toMatch(
      /download was interrupted/i,
    );
    expect(updaterStateForError(new Error("network timeout")).message).toMatch(
      /reach the release server/i,
    );
  });
});
