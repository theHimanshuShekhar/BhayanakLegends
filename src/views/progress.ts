import { progress } from "../data/mock";
import { avatar, bar } from "./ui";

function rankCard(): string {
  const r = progress.rank;
  return `<div class="flex items-center gap-4 rounded-2xl bg-linear-to-br from-[#2b2650] to-rc-s1 p-4 shadow-z2 ring-1 ring-rc-acc/30">
    <div class="grid h-[54px] w-[54px] place-items-center rounded-full bg-rc-acc text-[15px] font-bold text-rc-deep shadow-[0_0_26px_-4px_rgba(145,132,217,.8)]">E2</div>
    <div class="min-w-0 flex-1">
      <div class="text-[16px] font-bold text-rc-acc">${r.tier}</div>
      <div class="mt-0.5 text-[10px] text-rc-dim">${r.lp}</div>
    </div>
    <span class="pill-teal">Climbing</span>
  </div>`;
}

function historyCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Rank history · 6 months</div>
      <span class="pill-s2">2026</span>
    </div>
    <svg viewBox="0 0 660 130" class="h-[130px] w-full">
      <defs>
        <linearGradient id="histFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#9184d9" stop-opacity=".3"/>
          <stop offset="1" stop-color="#9184d9" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${[26, 52, 78, 104]
        .map(
          (y) =>
            `<line x1="0" y1="${y}" x2="660" y2="${y}" stroke="rgba(233,233,237,.07)" stroke-dasharray="3 5"/>`
        )
        .join("")}
      <polygon points="0,130 ${progress.history.points} 660,130" fill="url(#histFill)"/>
      <polyline points="${progress.history.points}" fill="none" stroke="#9184d9" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="620" cy="26" r="3.5" fill="#9184d9"/>
    </svg>
    <div class="mt-2 flex justify-between text-[9px] text-rc-dimmer">
      ${progress.history.months.map((m) => `<span>${m}</span>`).join("")}
    </div>
  </div>`;
}

function statCard(s: (typeof progress.stats)[number]): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-2 flex items-baseline justify-between">
      <span class="section-title">${s.label}</span>
      <span class="mono-n text-[11px] font-bold ${s.deltaTone === "teal" ? "text-rc-teal" : "text-rc-red"}">${s.delta}</span>
    </div>
    <div class="mb-2.5 text-[26px] font-bold leading-none ${s.valueTone === "red" ? "text-rc-red" : s.valueTone === "teal" ? "text-rc-teal" : "text-rc-soft"}">${s.value}</div>
    <div class="relative">
      ${bar(s.barPct, s.barTone)}
      <div class="absolute inset-y-0 w-px bg-rc-soft/80" style="left:${s.markPct}%"></div>
    </div>
    <div class="mt-1.5 flex justify-between text-[9px]">
      <span class="text-rc-dimmer">You</span>
      <span class="text-rc-dim">${s.benchmark}</span>
    </div>
  </div>`;
}

function weaknessCard(): string {
  const w = progress.weakness;
  const max = Math.max(...w.cols.map((c) => c.pct));
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Deaths by game minute</div>
    <div class="flex h-[92px] items-end gap-2">
      ${w.cols
        .map(
          (c) => `<div class="flex flex-1 flex-col items-center gap-1">
            <span class="mono-n text-[9px] font-semibold ${c.hot ? "text-rc-red" : "text-rc-dim"}">${c.pct}%</span>
            <div class="w-full rounded-t-md ${c.hot ? "bg-linear-to-t from-rc-red/70 to-rc-red shadow-[0_0_16px_-2px_rgba(229,115,143,.8)]" : "bg-rc-s3"}" style="height:${(c.pct / max) * 78 + 6}%"></div>
            <span class="text-[8.5px] text-rc-dimmer">${c.label}</span>
          </div>`
        )
        .join("")}
    </div>
    <p class="mt-3 rounded-xl bg-rc-red-lo/40 px-3 py-2 text-[10.5px] leading-[1.55] text-[#f4c3ce] shadow-z1">${w.text}</p>
  </div>`;
}

function rolesCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Role split</div>
    <div class="flex flex-col gap-3">
      ${progress.roles
        .map(
          (r) => `<div>
            <div class="mb-1.5 flex items-center justify-between text-[10px]">
              <span class="font-semibold">${r.label}</span>
              <span class="mono-n text-rc-dim">${r.wr}</span>
            </div>
            ${bar(r.pct, r.tone === "acc" ? "acc" : "s3")}
          </div>`
        )
        .join("")}
    </div>
    <p class="mt-3 rounded-xl bg-rc-teal-lo/40 px-3 py-2 text-[10.5px] leading-[1.5] text-rc-teal shadow-z1">${progress.roleTip}</p>
  </div>`;
}

function drillRow(d: (typeof progress.drills)[number]): string {
  const icon =
    d.state === "done"
      ? '<span class="grid h-[22px] w-[22px] place-items-center rounded-full bg-rc-teal text-[11px] font-bold text-rc-deep">✓</span>'
      : d.state === "focus"
        ? '<span class="grid h-[22px] w-[22px] place-items-center rounded-full ring-1 ring-rc-acc text-[9px] font-bold text-rc-acc">NOW</span>'
        : '<span class="grid h-[22px] w-[22px] place-items-center rounded-full bg-rc-s3 text-[9px] font-bold text-rc-dimmer">•</span>';
  const dim = d.state === "todo" ? "opacity-70" : "";
  return `<div class="flex items-center gap-3 rounded-xl bg-rc-s2 px-3 py-2.5 shadow-z1 ${dim}">
    ${icon}
    <div class="min-w-0 flex-1">
      <div class="text-[11.5px] font-semibold ${d.state === "done" ? "text-rc-dim" : d.state === "focus" ? "text-rc-acc" : ""}">${d.title}</div>
      <div class="truncate text-[9px] text-rc-dimmer">${d.sub}</div>
    </div>
  </div>`;
}

function poolRow(p: (typeof progress.pool)[number]): string {
  return `<div class="flex items-center gap-2.5 rounded-xl bg-rc-s2 px-3 py-2 shadow-z1">
    ${avatar(p.initials, "h-8 w-8 text-[10px]", p.wrTone === "teal" ? "teal" : "plain")}
    <div class="min-w-0 flex-1">
      <div class="text-[11.5px] font-semibold">${p.name}</div>
      <div class="text-[9px] text-rc-dimmer">${p.games}</div>
    </div>
    <span class="mono-n text-[13px] font-bold ${p.wrTone === "teal" ? "text-rc-teal" : p.wrTone === "red" ? "text-rc-red" : "text-rc-soft"}">${p.wr}</span>
  </div>`;
}

function recentRow(g: (typeof progress.recent.games)[number]): string {
  const win = g.result === "win";
  return `<div class="flex items-center gap-2.5 rounded-xl px-3 py-2 shadow-z1 ${win ? "bg-rc-s2/80 ring-1 ring-rc-teal/25" : "bg-rc-s2/50"}">
    <span class="h-[26px] w-[8px] rounded-full ${win ? "bg-rc-teal" : "bg-rc-red"}"></span>
    <div class="min-w-0 flex-1">
      <div class="text-[11px] font-semibold">${g.champ}</div>
      <div class="mono-n text-[9px] text-rc-dimmer">${g.score}</div>
    </div>
    <span class="mono-n text-[11px] font-bold ${win ? "text-rc-teal" : "text-rc-red"}">${g.lp}</span>
  </div>`;
}

export function renderProgress(): string {
  return `<div class="view-enter flex flex-col gap-4">
    <div class="flex items-center justify-between">
      <div class="section-title">Progress · Emerald II</div>
      <div class="flex items-center gap-1.5">
        <span class="pill-acc">Last 20</span>
        <span class="pill-s2">Season</span>
        <span class="pill-outline">Lifetime</span>
      </div>
    </div>
    <div class="grid grid-cols-[1fr_336px] items-start gap-4">
      <div class="flex flex-col gap-4">
        ${rankCard()}
        ${historyCard()}
        <div class="grid grid-cols-2 gap-4">${progress.stats.map(statCard).join("")}</div>
        ${weaknessCard()}
        ${rolesCard()}
      </div>
      <div class="flex flex-col gap-4">
        <div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
          <div class="mb-3 flex items-center justify-between">
            <div class="section-title">This week's drills</div>
            <span class="pill-s2">1 / 3</span>
          </div>
          <div class="flex flex-col gap-2">${progress.drills.map(drillRow).join("")}</div>
        </div>
        <div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
          <div class="mb-3 flex items-center justify-between">
            <div class="section-title">Champion pool</div>
            <span class="text-[9px] text-rc-dimmer">Most played · 2026</span>
          </div>
          <div class="flex flex-col gap-2">${progress.pool.map(poolRow).join("")}</div>
        </div>
        <div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
          <div class="mb-3 flex items-center justify-between">
            <div class="section-title">Recent games</div>
            <span class="pill-teal">${progress.recent.record}</span>
          </div>
          <div class="flex flex-col gap-2">${progress.recent.games.map(recentRow).join("")}</div>
          <button class="pill-outline mt-3 w-full cursor-pointer justify-center py-2 text-[10px] transition-colors hover:text-rc-soft">All 428 games</button>
        </div>
      </div>
    </div>
  </div>`;
}
