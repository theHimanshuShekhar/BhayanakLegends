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
    const signature = updaterStateForError(new Error("pubkey verification failed"));
    expect(signature).toMatchObject({ status: "failed", kind: "signature" });
    expect(signature.message).toMatch(/signature.*verified/i);
    expect(updaterStateForError(new Error("unsupported target architecture"))).toMatchObject({
      kind: "platform",
      message: expect.stringMatching(/platform or architecture/i),
    });
    expect(updaterStateForError(new Error("malformed JSON metadata"))).toMatchObject({
      kind: "metadata",
      message: expect.stringMatching(/metadata is malformed/i),
    });
    expect(updaterStateForError(new Error("version is older than current install"))).toMatchObject({
      kind: "version",
      message: expect.stringMatching(/version is not compatible/i),
    });
    expect(updaterStateForError(new Error("download interrupted"))).toMatchObject({
      kind: "download",
      message: expect.stringMatching(/download was interrupted/i),
    });
    expect(updaterStateForError(new Error("network timeout"))).toMatchObject({
      kind: "network",
      message: expect.stringMatching(/reach the release server/i),
    });
  });
});
