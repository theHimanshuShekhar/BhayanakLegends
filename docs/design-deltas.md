# Design ↔ Code Deltas

Where the claude.design artifact ("Rift Coach" v0.1, `~/downloads/League of Legends companion app.zip`) and the shipped app differ. Compiled after the fidelity port (champ-select, live-match, post-game, champions, progress, history). Discussion list — each item is a decision, not yet a ticket.

## Global chrome

| # | Design | App | Why |
|---|--------|-----|-----|
| G1 | Brand "RIFT COACH", user tag "vexlily #euw" | "BHAYANAK LEGENDS", "friends-first · 26k games" | Deliberate: product was renamed after the artifact was drawn. User tag should eventually bind to Settings riot_id. |
| G2 | Nav order: Live match · Post-game · Progress · Champions · History | Live match · **Champ select** · Post-game · Progress · Champions · History | Champ select is its own route in the app; the design folds it into the live window. |
| G3 | Window dots are decorative (red dot implies close) | First dot repurposed as live sidecar status LED (teal/red) | Functional swap; design intent preserved otherwise. |
| G4 | Status chips: "CHAMP SELECT SESSION" / "WEB API · ranks" / "FINDINGS PACK · 26k games" always lit | Single "sidecar" chip (connection state) + "Findings Pack · 26k games" | Session/API chips only make sense when those sources are live; idle states would be fake-lit. |
| G5 | `.pill` padding 3px 10px | 5px 11px (shared `design-system.css`) | Slightly larger; shared class was frozen during parallel porting. One-line fix if wanted. |
| G6 | Left sidebar (v1 pre-port) | **Resolved** — app now uses the design's topbar + nav pills. | — |

## 3a Champ select

| # | Design | App | Why |
|---|--------|-----|-----|
| A1 | Ban strip: 10 champion tiles with avatars/initials, "YOU hovering" highlighted slot, red "your lane" enemy slot, "ACTION 7 OF 20 · 0:24" timer | Idle: slim banner ("champion-level intel only" + "waiting for client"). Active: role/phase rows, "?" tiles, no timer countdown | LCU champ-select roster/timer data doesn't exist yet; idle honesty beats fake tiles. Timer needs LCU session clock. |
| A2 | YOUR LANE card: Syndra tile, 43% YOU WIN, OUTRANGES YOU / LVL 6 BURST tags, "your 41 games vs her" | Idle card: "Lock in to see your lane matchup", gradient/tile kept | Personal matchup WR needs the user's history joined to a locked opponent; arrives with live session + personal matchups. |
| A3 | SUGGESTED PICKS hero "Taliyah — 57% VS SYNDRA, 58% YOUR WR" | Real pack hero (currently highest-WR S/A MIDDLE) with "VS FIELD" win rate + "PICK RATE" second stat | No personal-vs-opponent stat exists at v1; pack numbers are population-level. Labels state the basis. |
| A4 | HOW TO PLAY IT: EARLY/MID/LATE advice rows (Syndra-specific) | Idle placeholder copy | Those lines are champion-matchup coaching; no pack source for generic ones without inventing. Could be driven per-champion from findings later. |
| A5 | COMP READ: "FRONTLINE HEAVY" tag + 72% AD / 28% AP bar + verdict line | Structure kept; neutral bar + idle caption | Damage-mix needs a live comp (LCU) or pack comp-fit finding (absent in pack v1). |
| A6 | LOADOUT: Electrocute + Flash/TP, "Apply page" writes to client | Same visuals, disabled + tooltip | LCU write path not built (and per-user consent/ToS care needed). |
| A7 | YOUR SIDE · RANKED: Ornn/Viego/Jhin with M7/M5/M6 badges, E4/E2/P1 ranks | Idle muted role rows (active: role+phase pills, no names) | Roster/rank/mastery data needs LCU + league-v4; names also policy-gated in ranked. |
| A8 | Mastery card numbers (50.6/46.9/+3.7pp) hardcoded in mock | Parsed live from pack `mastery_premium` finding | Same numbers today, but pack-driven now. |

## 3b Live match

| # | Design | App | Why |
|---|--------|-----|-----|
| L1 | Player list: 10 named rows, level/K-D-A/CS/ward score | Header + score strip kept; 3 dash skeleton rows + "waiting for :2999" pill | Live Client Data API unreachable without a running game; honesty rule bans fake rosters. |
| L2 | Score strip "13 — 9 kills · 5 — 3 turrets" live | Structure kept, dash placeholders | Same — needs live game. |
| L3 | WIN PROBABILITY: scrubable curve w/ event deltas (+6pp dragon etc.) | Nearest checkpoint bucket, big number, "Checkpoint estimate · Diagnostic" + "calibrated model ships with the next pack" | Model artifacts (Honest Model) not in pack v1; static checkpoint interpolation only. Scrubber needs the WP curve table. |
| L4 | EVENT FEED rows with +pp deltas (ChampionKill, DragonKill…) | Panel structure, "lands with the LCU bridge" | Needs live event stream. |
| L5 | ITEM VALUE BY PLAYER bars (7,900 / 6,400…) | Idle caption panel | Needs live inventory. |
| L6 | ENEMY SPELLS: "Flash 3:04", Zhonya's advice | Panel + policy note only — **no enemy timers, ever** | Riot March-2025 policy: enemy ability/item tracking is bannable. Design artifact violates it; app deliberately doesn't. |
| L7 | DEAD RIGHT NOW tile | Idle caption | Needs live state. |
| L8 | ACTIVE PLAYER health/level/gold + MID cheat-sheet | Idle captions | Needs live state. |
| L9 | Clock "14:22" ticking | 0:00 + "waiting for :2999" (ticks when live) | No game, no clock. |

## 3c Champions

| # | Design | App | Why |
|---|--------|-----|-----|
| C1 | Header champion (Taliyah-style) w/ BAN rate cell | Real tier-list header; BAN cell "—" unless champion is in pack ban_advisor | Pack v1 ban table covers ban-advisor picks, not all champions. |
| C2 | WHEN THE ENEMY TEAM HAS… comp rows | Omitted | No comp-fit findings in pack v1 (omit-don't-invent). |
| C3 | DAMAGE-FIT SCORE 0.71 | Omitted | Same. |
| C4 | BUILD ORDER rows (Everfrost → Shadowflame → Zhonya's 56.8%) | Structure + approximate-v1 caveat + "lands after Data-Dragon item refresh" | Build-order table not yet exported into the pack. |
| C5 | ITEM SPIKE TIMING: win rate by completion-minute chart | Sparkline of rolling WR per patch (real trajectories) in the same slot | Spike-timing table not in pack v1; slot kept alive with real personal data instead. |
| C6 | GOLD WASTE 340g vs 190g | Omitted | Finding absent from pack v1. |
| C7 | Matchup label "57% ±2.1" (70px) | "57% ±2.1 · 41 games" (112px, wraps less) | Games count added for honesty; width tradeoff. |

## 3d Progress

| # | Design | App | Why |
|---|--------|-----|-----|
| P1 | Rank card "Emerald II · 47 LP · +112 this month" + 6-month rank history chart | PERSONAL HISTORY card (matches, WR, patches) + trajectory sparkline | Rank/LP needs league-v4 integration (Riot API) — not built; rank history needs ranked-only series. |
| P2 | Lever adoption rows with filled trend bars | 4 real habit rows, bars neutral + "timeline features land with the loltrends wheel" | Habit trends need timeline-derived features (recall safety etc.) not yet extracted app-side. |
| P3 | Lane conversion card with real gap numbers | Renders real `lane_win_conversion_gap` finding | Matches. |
| P4 | What-if simulator with draggable sliders + predicted WR | Design-exact panel, inputs disabled, "activates with the model-bearing pack" | What-if needs the Honest Model artifact. |
| P5 | DEATHS BY GAME MINUTE chart | Idle caption panel | Needs timeline event extraction app-side (data exists in dev-import timelines; feature not wired). |
| P6 | Benchmark bars (CS/min vs Emerald median) | Real bars from pack benchmarks × personal medians (median tick on bar) | Matches, with real data. |
| P7 | Recent games / leaderboard rail cards | Omitted | No digest-list or leaderboard endpoint yet. |

## 3e Post-game

| # | Design | App | Why |
|---|--------|-----|-----|
| E1 | Verdict header w/ KDA/tier/patch tail line | Verdict tile + champion/role/duration (digest fields only) | Digest payload lacks KDA tail; extendable. |
| E2 | COMEBACK ODDS bound to the played game's deficit | Bound: digest `gold_diff_15` → nearest pack bucket (e.g. −593.5g → 27.6% "1 in 4") | Matches — actually ahead of the mock (real binding). |
| E3 | OBJECTIVE READ / SURRENDER READ prose | Objective read real; surrender read structure + "ships with the next Findings Pack" + survivorship note | Surrender Advisor model not in pack v1. |
| E4 | Scrubable WP mini-chart in review | Absent | Same model gap as L3. |

## Test debt from the port (immediate, mechanical)

- `e2e/smoke.spec.ts`: 4 assertions now stale — comeback "27.6%" moved into the post-game comeback card (was live screen), champ-select idle copy changed ("champion-level intel only"), champions default role no longer shows Lillia first, progress heading "Rolling win rate per patch" replaced by design-styled panels. Update selectors to the new design copy.

## Deliberate non-goals (policy, not gaps)

- Enemy summoner names in ranked champ select — never (Riot policy).
- Enemy ability/item timers — never (Riot March-2025 policy). The artifact's ENEMY SPELLS panel is rendered as structure + policy note only.
