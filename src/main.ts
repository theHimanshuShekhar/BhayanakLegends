import "./styles.css";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { getVersion } from "@tauri-apps/api/app";
import { renderLive } from "./views/live";
import { renderProgress } from "./views/progress";
import { renderPlaceholder } from "./views/placeholders";
import { rank, summoner } from "./data/mock";

type View = "live" | "progress" | "champions" | "history";
type Phase = "select" | "game";

const viewEl = document.querySelector<HTMLElement>("#view")!;
const navEl = document.querySelector<HTMLElement>("#nav-pills")!;
const devEl = document.querySelector<HTMLElement>("#dev-toggle")!;
const bannerEl = document.querySelector<HTMLElement>("#update-banner")!;
const labelEl = document.querySelector<HTMLElement>("#update-label")!;
const installBtn =
  document.querySelector<HTMLButtonElement>("#update-install")!;

let view: View = "live";
let phase: Phase = "select";
let downloading = false;

const views: { key: View; label: string }[] = [
  { key: "live", label: "Live match" },
  { key: "progress", label: "Progress" },
  { key: "champions", label: "Champions" },
  { key: "history", label: "History" },
];

function render() {
  const html =
    view === "live"
      ? renderLive(phase)
      : view === "progress"
        ? renderProgress()
        : view === "champions"
          ? renderPlaceholder(
              "Champions",
              "Champion-by-champion stats: matchups, builds and notes for every champ you queue."
            )
          : renderPlaceholder(
              "History",
              "Your full match history with coaching notes per game, once live data is wired."
            );
  viewEl.innerHTML = html;
  navEl.innerHTML = views
    .map(
      (v) =>
        `<button data-view="${v.key}" class="pill cursor-pointer px-3.5 py-[6px] text-[10.5px] transition-all ${v.key === view ? "pill-acc" : "pill-outline hover:text-rc-soft"}">${v.label}</button>`
    )
    .join("");
  navEl.querySelectorAll("[data-view]").forEach((b) =>
    b.addEventListener("click", () => {
      view = b.getAttribute("data-view") as View;
      render();
    })
  );
  renderDevToggle();
}

function renderDevToggle() {
  if (!import.meta.env.DEV) return;
  devEl.classList.remove("hidden");
  devEl.innerHTML = ["select", "game"]
    .map(
      (p) =>
        `<button data-phase="${p}" class="pill cursor-pointer px-2.5 py-[4px] text-[9px] ${phase === p ? "pill-acc" : "pill-outline"}">${p === "select" ? "1a · select" : "1e · in-game"}</button>`
    )
    .join("");
  devEl.querySelectorAll("[data-phase]").forEach((b) =>
    b.addEventListener("click", () => {
      phase = b.getAttribute("data-phase") as Phase;
      render();
    })
  );
}

async function checkForUpdates() {
  try {
    const update = await check();
    if (!update) return;
    labelEl.textContent = `Update available: v${update.version} (installed: v${await getVersion()})`;
    bannerEl.classList.remove("hidden");
    installBtn.addEventListener("click", async () => {
      if (downloading) return;
      downloading = true;
      labelEl.textContent = "Downloading update...";
      try {
        await update.downloadAndInstall(() => {});
        await relaunch();
      } catch (err) {
        labelEl.textContent = `Update failed: ${err}`;
        downloading = false;
      }
    });
  } catch {
    // offline or not packaged — updates are a bonus, never an error state
  }
}

document.querySelector<HTMLElement>("#summoner-label")!.textContent = summoner;
document.querySelector<HTMLElement>("#rank-label")!.textContent = rank;

render();
checkForUpdates();
