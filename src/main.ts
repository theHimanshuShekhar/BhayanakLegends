import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { getVersion } from "@tauri-apps/api/app";

const statusEl = document.querySelector<HTMLElement>("#update-status");
const bannerEl = document.querySelector<HTMLElement>("#update-banner");
const messageEl = document.querySelector<HTMLElement>("#update-message");
const updateBtn = document.querySelector<HTMLButtonElement>("#update-btn");
const checkBtn = document.querySelector<HTMLButtonElement>("#check-btn");

let downloading = false;

function setStatus(text: string) {
  if (statusEl) statusEl.textContent = text;
}

function showBanner(text: string) {
  if (bannerEl) bannerEl.classList.remove("hidden");
  if (messageEl) messageEl.textContent = text;
}

async function checkForUpdates(manual = false) {
  if (downloading) return;
  if (!manual) setStatus("Checking for updates...");
  try {
    const update = await check();
    if (!update) {
      setStatus(`Up to date (v${await getVersion()})`);
      return;
    }
    showBanner(
      `Update available: v${update.version} (installed: v${await getVersion()})`
    );
    updateBtn?.addEventListener("click", async () => {
      if (downloading) return;
      downloading = true;
      setStatus("Downloading update...");
      try {
        await update.downloadAndInstall((event) => {
          if (event.event === "Progress") {
            setStatus(`Downloading... ${event.data.chunkLength} bytes chunk`);
          }
        });
        setStatus("Update installed, restarting...");
        await relaunch();
      } catch (err) {
        downloading = false;
        setStatus(`Update failed: ${err}`);
      }
    });
  } catch (err) {
    if (manual) setStatus(`Update check failed: ${err}`);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  checkBtn?.addEventListener("click", () => checkForUpdates(true));
  checkForUpdates();
});