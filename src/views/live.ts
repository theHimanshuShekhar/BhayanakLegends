import {
  draft,
  lane,
  picks,
  comp,
  build,
  enemySummoners,
  objectives,
  bans,
  live,
  type Chip,
  type PlayerLine,
  type Tip,
} from "../data/mock";
import { avatar, bar } from "./ui";

function chip(c: Chip): string {
  const tone = c.you ? "acc" : c.enemyLane ? "enemy" : "plain";
  const wrap = c.you
    ? "bg-rc-acc/15 shadow-[0_0_20px_-4px_rgba(145,132,217,.6)]"
    : c.enemyLane
      ? "bg-rc-red/10"
      : "bg-rc-s2/70";
  return `<div class="flex min-w-0 items-center gap-2.5 rounded-xl px-2.5 py-2 ${wrap} ${c.dim ? "opacity-50" : ""}">${avatar(c.initials, "h-8 w-8 text-[11px]", tone)}<div class="min-w-0 flex-1"><div class="truncate text-[12px] font-semibold">${c.name}</div><div class="truncate text-[9.5px] text-rc-dim">${c.sub}</div></div></div>`;
}

function tipRow(t: Tip): string {
  const tone =
    t.phaseTone === "teal"
      ? "pill-teal"
      : t.phaseTone === "amber"
        ? "pill-amber"
        : t.phaseTone === "blue"
          ? "pill-blue"
          : "pill-acc";
  return `<div class="flex items-start gap-3"><span class="${tone} mt-[1px]">${t.phase}</span><p class="text-[11px] leading-[1.55] text-rc-dim">${t.text}</p></div>`;
}

function laneCard(): string {
  return `<div class="rounded-2xl bg-linear-to-br from-[#2a1822] to-rc-s1 p-4 shadow-z2">
    <div class="mb-3 flex items-center gap-2.5">
      <span class="pill-red">Your lane</span>
      <span class="text-[10px] text-rc-dim">${lane.sampled}</span>
    </div>
    <div class="flex items-center gap-3">
      ${avatar(lane.enemyInitials, "h-14 w-14 text-lg", "red")}
      <div class="min-w-0 flex-1">
        <div class="text-[15px] font-bold">${lane.enemyName}</div>
        <div class="mt-0.5 truncate text-[10px] text-rc-dim">${lane.enemySub}</div>
      </div>
      <div class="text-right">
        <div class="text-[24px] font-bold leading-none text-rc-red">${lane.youWin}</div>
        <div class="mt-1 text-[9px] text-rc-dim">YOU WIN</div>
      </div>
    </div>
    <div class="mt-3 flex items-center gap-2">
      ${bar(43, "red", "flex-1")}
      ${bar(57, "s3", "flex-1")}
    </div>
    <div class="mt-3 flex flex-wrap gap-1.5">
      ${lane.pills
        .map(
          (p) =>
            `<span class="${p.tone === "red" ? "pill-red" : p.tone === "amber" ? "pill-amber" : "pill-s2"}">${p.label}</span>`
        )
        .join("")}
    </div>
  </div>`;
}

function howToCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">How to play it</div>
    <div class="flex flex-col gap-3.5">${lane.tips.map(tipRow).join("")}</div>
  </div>`;
}

function heroPick(): string {
  const h = picks.hero;
  return `<div class="rounded-[20px] bg-linear-to-br from-[#2b2650] to-rc-s2 p-4 shadow-z3 ring-1 ring-rc-acc/40">
    <div class="flex items-center gap-4">
      ${avatar(h.initials, "h-[74px] w-[74px] text-[26px]", "acc")}
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span class="text-[19px] font-bold">${h.name}</span>
          <span class="pill-teal">Best pick</span>
        </div>
        <div class="mt-1 text-[10px] text-rc-dim">vs ${lane.enemyName} · 34 games this season · Mid</div>
        <p class="mt-2 text-[11px] leading-[1.5] text-rc-dim">${h.reason}</p>
      </div>
      <div class="flex flex-col gap-2">
        <div class="rounded-xl bg-rc-deep/70 px-3 py-2 text-center shadow-z1">
          <div class="text-[9px] text-rc-dim">${h.vsLabel}</div>
          <div class="text-[17px] font-bold text-rc-teal">${h.vsValue}</div>
        </div>
        <div class="rounded-xl bg-rc-deep/70 px-3 py-2 text-center shadow-z1">
          <div class="text-[9px] text-rc-dim">${h.yourLabel}</div>
          <div class="text-[17px] font-bold text-rc-teal">${h.yourValue}</div>
        </div>
      </div>
    </div>
  </div>`;
}

function pickCard(p: (typeof picks)["cards"][number]): string {
  return `<div class="rounded-xl bg-rc-s2 p-3 shadow-z1 ${p.dim ? "opacity-70" : ""}">
    <div class="flex items-center gap-2.5">
      ${avatar(p.initials, "h-10 w-10 text-[13px]", p.dim ? "plain" : "teal")}
      <div class="min-w-0">
        <div class="text-[13px] font-bold">${p.name}</div>
        <div class="text-[9.5px] text-rc-dim">${p.sub}</div>
      </div>
    </div>
    <div class="mt-2.5 flex items-center gap-1.5">
      <span class="${p.vsTone === "teal" ? "pill-teal" : "pill-red"}">${p.vs}</span>
      <span class="${p.tagTone === "amber" ? "pill-amber" : "pill-s2"}">${p.tag}</span>
    </div>
    <p class="mt-2 text-[10px] leading-[1.5] text-rc-dim">${p.note}</p>
  </div>`;
}

function compCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Team comp</div>
      <span class="pill-amber">${comp.pill}</span>
    </div>
    <div class="flex flex-col gap-3">
      ${comp.bars
        .map(
          (b) => `<div>
            <div class="mb-1.5 flex items-center justify-between text-[9.5px]">
              <span class="text-rc-dim">${b.label}</span>
              <span class="font-semibold text-rc-soft">${b.value}</span>
            </div>
            ${bar(b.pct, b.tone)}
          </div>`
        )
        .join("")}
    </div>
    <p class="mt-3 text-[10.5px] leading-[1.55] text-rc-dim">${comp.note}</p>
  </div>`;
}

function buildCard(): string {
  const slots = Array.from({ length: build.slots }, (_, i) => i);
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Build</div>
      <span class="pill-teal">${build.pill}</span>
    </div>
    <div class="flex items-center gap-1.5">
      ${slots
        .map(
          (i) =>
            `<div class="grid h-[34px] w-[34px] place-items-center rounded-lg shadow-[inset_0_2px_5px_rgba(0,0,0,.8)] ${i === build.accSlot ? "bg-rc-acc text-rc-deep text-[13px] font-bold" : "bg-rc-deep"}" ${i === build.accSlot ? "" : 'aria-hidden="true"'}></div>`
        )
        .join("")}
    </div>
    <div class="mt-3 rounded-xl bg-rc-acc-lo/30 px-3 py-2 text-[10.5px] leading-[1.5] text-rc-soft shadow-z1">${build.advice}</div>
    <div class="mt-3 grid grid-cols-2 gap-2">
      <div class="rounded-xl bg-rc-deep px-3 py-2 shadow-z1">
        <div class="text-[9px] text-rc-dim">KEYSTONE</div>
        <div class="mt-0.5 text-[11px] font-semibold text-rc-acc">${build.keystone}</div>
      </div>
      <div class="rounded-xl bg-rc-deep px-3 py-2 shadow-z1">
        <div class="text-[9px] text-rc-dim">SECONDARY</div>
        <div class="mt-0.5 text-[11px] font-semibold text-rc-acc">${build.secondary}</div>
      </div>
    </div>
  </div>`;
}

function suggestedPicks(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-4 flex items-center justify-between gap-3">
      <div class="section-title">Suggested picks</div>
      <div class="flex items-center gap-1.5">
        <span class="pill-acc">Your pool</span>
        <span class="pill-s2">Meta</span>
        <span class="pill-outline">Counters</span>
      </div>
      <span class="text-[9.5px] text-rc-dim">VS ${lane.enemyName.toUpperCase()} · EMERALD</span>
    </div>
    ${heroPick()}
    <div class="mt-3 grid grid-cols-3 gap-3">${picks.cards.map(pickCard).join("")}</div>
  </div>`;
}

function summonersCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Enemy summoners</div>
    <div class="flex flex-col gap-2.5">
      ${enemySummoners.rows
        .map(
          (r) => `<div class="flex items-center gap-2.5">
            ${avatar(r.initials, "h-[26px] w-[26px] text-[9px]", r.iconTone === "red" ? "red" : "enemy")}
            <span class="w-14 text-[11px] font-semibold">${r.name}</span>
            ${r.spells
              .map(
                (s) =>
                  `<span class="${s.tone === "blue" ? "pill-blue" : s.tone === "amber" ? "pill-amber" : "pill-s2"}">${s.label}</span>`
              )
              .join("")}
          </div>`
        )
        .join("")}
    </div>
    <p class="mt-3 text-[9.5px] leading-[1.5] text-rc-dimmer">${enemySummoners.note}</p>
  </div>`;
}

function objectivesCard(
  rows = objectives.rows,
  title = "Objective plan"
): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">${title}</div>
    <div class="flex flex-col gap-2">
      ${rows
        .map(
          (
            o
          ) => `<div class="flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${o.hot ? "bg-rc-teal-lo/60 shadow-[0_0_18px_-6px_rgba(87,207,180,.6)]" : "bg-rc-s2 shadow-z1"}">
            <div class="min-w-0">
              <div class="text-[11.5px] font-semibold ${o.hot ? "text-rc-teal" : ""}">${o.name}</div>
              <div class="truncate text-[9px] text-rc-dim">${o.sub}</div>
            </div>
            <div class="mono-n text-[15px] font-bold ${o.hot ? "text-rc-teal" : "text-rc-soft"}">${o.time}</div>
          </div>`
        )
        .join("")}
    </div>
  </div>`;
}

function bansCard(): string {
  const tiles = Array.from({ length: bans }, (_, i) => i);
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Bans this lobby</div>
    <div class="grid grid-cols-6 gap-1.5">
      ${tiles
        .map(
          () =>
            `<div class="avatar-plain h-8 w-8 text-[9px] opacity-60 relative overflow-hidden">✕<span class="absolute inset-0 grid place-items-center text-[13px] text-rc-red/80" style="transform:rotate(0deg)">✕</span></div>`
        )
        .join("")}
    </div>
  </div>`;
}

function lockButtons(): string {
  return `<div class="flex flex-col gap-2">
    <button class="pill-acc cursor-pointer justify-center px-4 py-2.5 text-[12px] shadow-[0_5px_0_var(--color-rc-acc-lo),0_18px_30px_-10px_rgba(145,132,217,.7)] transition-transform hover:-translate-y-[1px] active:translate-y-[2px]">Lock Taliyah</button>
    <button class="pill-outline cursor-pointer justify-center px-4 py-2.5 text-[11px] transition-colors hover:text-rc-soft">Compare all picks</button>
  </div>`;
}

function scoreboardRow(p: PlayerLine, you: boolean): string {
  return `<div class="flex items-center gap-2.5 px-3 py-[7px] ${you ? "rounded-lg bg-rc-acc/12" : ""}">
    ${avatar(p.initials, "h-[26px] w-[26px] text-[9px]", you ? "acc" : "plain")}
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-1.5">
        <span class="text-[11px] font-semibold ${you ? "text-rc-acc" : ""}">${p.name}</span>
        ${you ? '<span class="pill-acc !px-1.5 !py-0 text-[8px]">You</span>' : ""}
      </div>
    </div>
    <div class="rounded-[6px] bg-rc-s3 px-1.5 py-[2px] text-[9px] font-bold text-rc-dim">${p.level}</div>
    <div class="mono-n text-[10px] text-rc-dim">${p.stats}</div>
  </div>`;
}

function scoreboard(team: PlayerLine[]): string {
  const rows = team
    .map((p) =>
      scoreboardRow(p, Boolean((p as PlayerLine & { you?: boolean }).you))
    )
    .join("");
  return `<div class="flex flex-col divide-y divide-rc-line rounded-2xl bg-rc-s2/60 p-2 shadow-z2">${rows}</div>`;
}

function goldCard(): string {
  const { points } = live.goldChart;
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Team gold difference</div>
      <span class="pill-teal">+2.4k gold</span>
    </div>
    <svg viewBox="0 0 660 90" class="h-[90px] w-full">
      <defs>
        <linearGradient id="goldFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#57cfb4" stop-opacity=".35"/>
          <stop offset="1" stop-color="#57cfb4" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <line x1="0" y1="45" x2="660" y2="45" stroke="rgba(233,233,237,.08)" stroke-dasharray="3 5"/>
      <polygon points="0,90 ${points} 660,90" fill="url(#goldFill)"/>
      <polyline points="${points}" fill="none" stroke="#57cfb4" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="660" cy="22" r="3" fill="#57cfb4"/>
    </svg>
    <div class="mt-2 flex justify-between text-[9px] text-rc-dimmer">
      <span>0:00</span><span>14:22</span>
    </div>
  </div>`;
}

function teamVsCard(): string {
  const b = live.team.bars;
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Team vs team</div>
    <div class="flex flex-col gap-3">
      ${b
        .map(
          (x) => `<div>
            <div class="mb-1.5 flex items-center justify-between text-[9.5px]">
              <span class="mono-n font-semibold text-rc-soft">${x.you}</span>
              <span class="text-rc-dim">${x.label}</span>
              <span class="mono-n font-semibold text-rc-red">${x.them}</span>
            </div>
            <div class="flex items-center gap-1">
              ${bar(x.youPct, x.youTone as "teal")}
              ${bar(x.themPct, x.themTone === "red" ? "red" : "s3")}
            </div>
          </div>`
        )
        .join("")}
    </div>
    <div class="mt-3 grid grid-cols-3 gap-2">
      ${live.team.boxes
        .map(
          (
            bx
          ) => `<div class="rounded-xl bg-rc-deep px-2 py-2 text-center shadow-z1">
            <div class="text-[8.5px] text-rc-dim">${bx.label}</div>
            <div class="mono-n text-[15px] font-bold ${bx.tone === "teal" ? "text-rc-teal" : bx.tone === "red" ? "text-rc-red" : "text-rc-soft"}">${bx.value}</div>
          </div>`
        )
        .join("")}
    </div>
  </div>`;
}

function powerCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Power curve</div>
      <span class="pill-teal">${live.power.pill}</span>
    </div>
    <svg viewBox="0 0 300 90" class="h-[90px] w-full">
      <line x1="0" y1="45" x2="300" y2="45" stroke="rgba(233,233,237,.08)" stroke-dasharray="3 5"/>
      <polyline points="${live.power.youPoints}" fill="none" stroke="#57cfb4" stroke-width="2.5" stroke-linecap="round"/>
      <polyline points="${live.power.themPoints}" fill="none" stroke="#e5738f" stroke-width="2" stroke-dasharray="4 4" stroke-linecap="round"/>
    </svg>
    <div class="mt-2 flex items-center gap-4 text-[9px] text-rc-dim">
      <span class="flex items-center gap-1.5"><span class="h-[3px] w-4 rounded-full bg-rc-teal"></span>Your team</span>
      <span class="flex items-center gap-1.5"><span class="h-[3px] w-4 rounded-full bg-rc-red"></span>Their team</span>
    </div>
    <p class="mt-2.5 text-[10.5px] leading-[1.55] text-rc-dim">${live.power.note}</p>
  </div>`;
}

function damageCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Damage by player</div>
    <div class="flex flex-col gap-2.5">
      ${live.damage
        .map(
          (d) => `<div class="flex items-center gap-2.5">
            ${avatar(d.initials, "h-[24px] w-[24px] text-[8.5px]", d.you ? "acc" : "plain")}
            <span class="w-16 truncate text-[10.5px] font-semibold ${d.you ? "text-rc-acc" : ""}">${d.name}</span>
            ${bar(d.pct, d.you ? "acc" : "s3", "max-w-[150px]")}
            <span class="mono-n ml-auto text-[10px] font-semibold text-rc-soft">${d.value}</span>
            <span class="w-8 text-right text-[9px] text-rc-dim">${d.pct}%</span>
          </div>`
        )
        .join("")}
    </div>
  </div>`;
}

function laneLiveCard(): string {
  const s = live.laneStats;
  return `<div class="rounded-2xl bg-linear-to-br from-[#2a1822] to-rc-s1 p-4 shadow-z2">
    <div class="mb-3 flex items-center gap-2.5">
      <span class="pill-red">Your lane</span>
      <span class="text-[10px] text-rc-dim">14:22 · Laning over</span>
    </div>
    <div class="flex items-center gap-3">
      ${avatar("TA", "h-11 w-11 text-[15px]", "acc")}
      <div class="text-[13px] font-bold text-rc-acc">Taliyah</div>
      <div class="mx-1 h-px flex-1 bg-rc-line"></div>
      ${avatar("SY", "h-11 w-11 text-[15px]", "red")}
      <div class="text-[13px] font-bold text-rc-red">Syndra</div>
    </div>
    <div class="mt-3 flex flex-col gap-2.5">
      ${s
        .map(
          (r) => `<div class="flex items-center gap-2">
            <span class="w-11 text-[9px] text-rc-dim">${r.label}</span>
            <span class="mono-n w-10 text-right text-[11px] font-bold ${r.youTone === "teal" ? "text-rc-teal" : r.youTone === "red" ? "text-rc-red" : "text-rc-soft"}">${r.you}</span>
            <div class="relative h-[7px] flex-1 overflow-hidden rounded-full bg-rc-deep shadow-[inset_0_2px_4px_rgba(0,0,0,.7)]">
              <div class="absolute inset-y-0 left-1/2 w-px bg-rc-line"></div>
              <div class="absolute inset-y-0 left-1/4 h-full rounded-full bg-rc-teal/80" style="width:${r.label === "CS" ? 47 : 52}%"></div>
              <div class="absolute inset-y-0 h-full rounded-full bg-rc-red/80" style="left:${r.label === "CS" ? 50 : 53}%;width:${r.label === "CS" ? 50 : 47}%"></div>
            </div>
            <span class="mono-n w-10 text-[11px] font-bold ${r.themTone === "teal" ? "text-rc-teal" : r.themTone === "red" ? "text-rc-red" : "text-rc-soft"}">${r.them}</span>
          </div>`
        )
        .join("")}
    </div>
    <p class="mt-3 rounded-xl bg-rc-red-lo/40 px-3 py-2 text-[10.5px] leading-[1.5] text-[#f4c3ce] shadow-z1">${live.laneNote}</p>
  </div>`;
}

function cdsCard(): string {
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="section-title mb-3">Enemy cooldowns</div>
    <div class="flex flex-col gap-2.5">
      ${live.cds
        .map(
          (r) => `<div class="flex items-center gap-2.5">
            ${avatar(r.initials, "h-[26px] w-[26px] text-[9px]", r.iconTone === "red" ? "red" : "enemy")}
            <span class="w-14 text-[11px] font-semibold">${r.name}</span>
            <span class="${r.a.tone === "teal" ? "pill-teal" : "pill-red"}">${r.a.label}</span>
            <span class="${r.b.tone === "amber" ? "pill-amber" : r.b.tone === "teal" ? "pill-teal" : "pill-s2"}">${r.b.label}</span>
          </div>`
        )
        .join("")}
    </div>
  </div>`;
}

function yourBuildCard(): string {
  const slots = Array.from({ length: live.build.slots }, (_, i) => i);
  return `<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1">
    <div class="mb-3 flex items-center justify-between">
      <div class="section-title">Your build</div>
      <span class="mono-n text-[13px] font-bold text-rc-teal">${live.build.gold}</span>
    </div>
    <div class="flex items-center gap-1.5">
      ${slots
        .map(
          (i) =>
            `<div class="grid h-[34px] w-[34px] place-items-center rounded-lg shadow-[inset_0_2px_5px_rgba(0,0,0,.8)] ${i < live.build.filled ? "bg-rc-acc/80 text-rc-deep text-[13px] font-bold" : "bg-rc-deep"}">${i < live.build.filled ? "✦" : ""}</div>`
        )
        .join("")}
    </div>
    <div class="mt-3 rounded-xl bg-rc-acc-lo/30 px-3 py-2 text-[10.5px] leading-[1.5] text-rc-soft shadow-z1">${live.build.advice}</div>
    <div class="mt-3 flex items-center justify-between">
      <span class="text-[10px] text-rc-dim">Deaths: <span class="font-semibold text-rc-soft">${live.build.deaths}</span></span>
      <button class="pill-s2 cursor-pointer !py-[5px] transition-colors hover:text-rc-soft">🔇 Mute all</button>
    </div>
  </div>`;
}

export function renderLive(phase: "select" | "game"): string {
  const strip =
    phase === "select"
      ? `<div class="grid grid-cols-[1fr_132px_1fr] items-stretch gap-4">
          <div class="grid grid-cols-5 gap-2">${draft.allies.map(chip).join("")}</div>
          <div class="flex flex-col items-center justify-center gap-1 rounded-2xl bg-linear-to-b from-rc-s2 to-rc-s1 px-4 py-3 shadow-z2">
            <div class="text-[9px] tracking-[0.14em] text-rc-dim">${draft.phase}</div>
            <div class="mono-n text-[24px] font-bold text-rc-acc">${draft.timer}</div>
            <div class="w-[120px]">${bar(draft.phasePct, "acc")}</div>
          </div>
          <div class="grid grid-cols-5 gap-2">${draft.enemies.map(chip).join("")}</div>
        </div>`
      : `<div class="grid grid-cols-[1fr_150px_1fr] items-stretch gap-4">
          ${scoreboard(live.allies)}
          <div class="flex flex-col items-center justify-center gap-1 rounded-2xl bg-linear-to-b from-rc-s2 to-rc-s1 px-4 py-3 shadow-z2">
            <div class="mono-n text-[22px] font-bold text-rc-teal">${live.timer}</div>
            <div class="text-[9px] tracking-[0.14em] text-rc-dim">${live.kills}</div>
            <div class="w-[110px]">${bar(live.goldPct, "teal")}</div>
            <span class="pill-teal">${live.gold}</span>
          </div>
          ${scoreboard(live.enemies)}
        </div>`;

  const body =
    phase === "select"
      ? `<div class="grid grid-cols-[352px_1fr_330px] gap-4">
          <div class="flex flex-col gap-4">${laneCard()}${howToCard()}</div>
          <div class="flex flex-col gap-4">${suggestedPicks()}<div class="grid grid-cols-2 gap-4">${compCard()}${buildCard()}</div></div>
          <div class="flex flex-col gap-4">${summonersCard()}${objectivesCard()}${bansCard()}${lockButtons()}</div>
        </div>`
      : `<div class="grid grid-cols-[352px_1fr_330px] gap-4">
          <div class="flex flex-col gap-4">${laneLiveCard()}<div class="rounded-2xl bg-rc-s1 p-4 shadow-z1"><div class="section-title mb-3">Coaching</div><div class="flex flex-col gap-3.5">${live.tips.map(tipRow).join("")}</div></div></div>
          <div class="flex flex-col gap-4">${goldCard()}${teamVsCard()}${powerCard()}${damageCard()}</div>
          <div class="flex flex-col gap-4">${objectivesCard(live.objTimers, "Objective timers")}${cdsCard()}${yourBuildCard()}</div>
        </div>`;

  return `<div class="view-enter flex flex-col gap-4">${strip}${body}</div>`;
}
