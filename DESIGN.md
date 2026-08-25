---
name: Bhayanak Legends
description: A calm, research-led League of Legends companion for live decisions and personal improvement.
colors:
  deep: "#0a0b16"
  bg: "#0e1020"
  surface: "#181b2e"
  surface-2: "#20243a"
  surface-3: "#2a2f49"
  line: "rgba(233, 233, 237, 0.1)"
  text: "#e9e9ed"
  dim: "#a8acbd"
  dimmer: "#9da1b5"
  accent: "#9184d9"
  accent-low: "#5d5294"
  danger: "#e5738f"
  danger-low: "#4d2436"
  teal: "#57cfb4"
  teal-low: "#1b463f"
  amber: "#e8b96b"
  amber-low: "#4a3a1c"
  info: "#7bb0ef"
  info-low: "#1e3350"
  soft-text: "#cfd3e5"
  soft-lavender: "#e0ddf5"
  soft-blue: "#cfe3f9"
  soft-rose: "#f4c3ce"
  chip-text: "#e7e5fe"
typography:
  headline:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.25
  title:
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "10.5px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace"
    fontSize: "9.5px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.11em"
rounded:
  sm: "6px"
  md: "10px"
  lg: "16px"
  xl: "20px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.deep}"
    rounded: "{rounded.pill}"
    padding: "10px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.deep}"
    rounded: "{rounded.pill}"
    padding: "10px 12px"
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "5px 9px"
  card-surface:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "12px"
  card-raised:
    backgroundColor: "{colors.surface-2}"
    rounded: "18px"
    padding: "13px"
  chip-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.deep}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
  chip-muted:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.dim}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
  field:
    backgroundColor: "{colors.deep}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
---

# Design System: Bhayanak Legends

## Overview

**Creative North Star: "The Tactical Instrument Panel"**

Bhayanak Legends is a compact instrument panel for high-context decisions. Its visual language is dense but calm: dark tonal layers keep attention on Findings Pack evidence, Personal History, and live status rather than on decoration. Inter Variable carries readable explanatory copy; JetBrains Mono makes labels, champion names, metrics, and state changes feel precise and inspectable.

The system uses restrained gradients, rounded cards, pill-shaped status controls, and small luminous state markers. Elevation is tactile rather than theatrical: surfaces step from deep canvas to raised container, while shadows give active or important panels a measured lift. The intended voice is research-led and confident without pretending that population evidence is certainty.

**Key Characteristics:**
- Dark tonal layering with a lavender primary signal and disciplined semantic accents.
- Compact monospace labels paired with short, readable explanatory copy.
- Rounded cards and pills that make dense information feel touchable and organized.
- Status colors communicate connection, evidence, caution, and personal trajectory.
- Calm, research-led presentation; avoid glossy esports spectacle and noisy dashboard ornament.

## Colors

The palette is a cool midnight field with one lavender action voice and small, semantic signals for live state and research interpretation.

### Primary
- **Instrument Lavender** (`{colors.accent}`): Primary navigation, selected roles, decisive actions, and the visual anchor for the user's current context.

### Secondary
- **Signal Teal** (`{colors.teal}`): Positive personal progress, confirmed live state, and favorable evidence without turning every success into a celebration.
- **Field Blue** (`{colors.info}`): Findings Pack and population evidence, kept separate from personal outcomes.

### Tertiary
- **Caution Amber** (`{colors.amber}`): Warnings, prerequisites, and conditions that need attention before an action is trustworthy.
- **Danger Rose** (`{colors.danger}`): Offline/error states and unfavorable matchup or outcome signals.

### Neutral
- **Midnight Canvas** (`{colors.bg}` / `{colors.deep}`): App background and deepest inset field.
- **Surface Tiers** (`{colors.surface}`, `{colors.surface-2}`, `{colors.surface-3}`): Tonal containers from ordinary card to raised panel to compact inset control.
- **Bright Text** (`{colors.text}`): Primary headings and values.
- **Quiet Text** (`{colors.dim}` / `{colors.dimmer}`): Supporting copy, metadata, and low-priority labels.
- **Soft Annotation Colors** (`{colors.soft-text}`, `{colors.soft-lavender}`, `{colors.soft-blue}`, `{colors.soft-rose}`): High-contrast copy on semantic fills.
- **Hairline** (`{colors.line}`): Subtle separators and control strokes; never a dominant frame.

### Named Rules
**The Two-Data-Worlds Rule.** Teal describes the player's Personal History and live confirmation; blue describes Findings Pack population evidence. Do not blur the two.

## Typography

**Display Font:** None; the product does not use oversized display typography.
**Body Font:** Inter Variable, Inter, system-ui, sans-serif
**Label/Mono Font:** JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace

**Character:** Inter keeps explanations approachable at compact sizes. JetBrains Mono turns labels, champion names, percentages, and system states into measured readouts. Weight and letter spacing create hierarchy more often than large type does.

### Hierarchy
- **Headline** (500, 18px, 1.25): Page titles and primary screen orientation.
- **Title** (600, 13px, 1.3): Champion names, card values, and compact data anchors.
- **Body** (400, 10.5px, 1.5): Explanatory findings, caveats, and guidance copy.
- **Label** (700, 9.5px, 1.2, 0.11em, uppercase): Kicker rows, section labels, and status vocabulary.

### Named Rules
**The Readout Hierarchy Rule.** Use scale, weight, and monospace contrast to make the next decision obvious; do not solve hierarchy with oversized marketing headlines.

## Layout

The app is a full-height vertical shell: a compact top bar, a pill-based primary navigation row, then a scrollable content screen. The shell keeps `14px` horizontal screen padding and `14px` bottom padding. Top bar rhythm is `10px 16px 8px`; navigation uses `2px 16px 10px`. Screen content commonly uses `12px` gaps, with internal card rhythm between `6px` and `13px`.

Content is composed from flexible grids and dense cards. Champ select collapses its multi-column layout to one column below `1100px`; horizontal chip rows may scroll rather than wrap. The interface prioritizes scanability and minimum interactive targets over decorative whitespace.

## Elevation & Depth

Depth is layered and tactile. The deep canvas and three surface tones establish the main hierarchy; shadows add restrained lift to cards, raised panels, connected status, and selected navigation. Gradients are sparse and directional, used on hero or raised surfaces to add atmosphere without becoming a background texture.

### Shadow Vocabulary
- **Low card lift** (`var(--shadow-z1)`): Standard cards, pills, and quiet status containers.
- **Raised panel lift** (`var(--shadow-z2)`): Raised cards, live companion surfaces, and high-priority containers.
- **Active control lift** (`0 3px 0 var(--color-accent-low), 0 8px 16px -6px rgba(145,132,217,.6)`): Selected navigation and primary actions; gives the control a tactile pressed-edge silhouette.

### Named Rules
**The Layer-Before-Shadow Rule.** Establish hierarchy with surface color first; use shadow to reinforce it, not to rescue a flat or ambiguous layout.

## Shapes

The form language is generously rounded but not bubbly. Ordinary cards use `16px` corners, raised cards use `18px`, hero surfaces reach `20px`, and compact controls use `6px` to `12px`. Pills are fully rounded (`999px`) and reserve their silhouette for statuses, navigation, role filters, and short actions. Hairline borders are translucent and subordinate to tonal contrast.

Focus is explicit and amber: interactive elements receive a `2px` outline with `2px` offset. Links and buttons retain at least `24px` minimum dimensions; checkbox and radio controls retain `24px` minimum dimensions.

## Components

### Buttons
- **Shape:** Pill-shaped for primary actions (`999px`); compact secondary controls use gently curved corners (`6px` to `10px`).
- **Primary:** Instrument Lavender fill, deep text, compact `10px 12px` padding, and a low accent edge/shadow for tactile lift.
- **Hover / Focus:** Preserve the accent role; use the amber `2px` focus outline and avoid adding a competing glow.
- **Secondary / Ghost / Tertiary:** Surface-2 fill with bright or dim text; borders stay subtle and the control never outshouts a primary action.

### Chips
- **Style:** Compact monospace labels with `5px 11px` padding and full pill corners. Semantic low fills (`accent-low`, `info-low`, `teal-low`, `amber-low`, `danger-low`) carry context.
- **State:** Active navigation and selected role chips use the accent fill; idle chips use Surface-2 or Surface-3 with dim text.

### Cards / Containers
- **Corner Style:** `16px` for standard cards; `18px` to `20px` for raised or hero panels.
- **Background:** Surface for ordinary cards; Surface-2 for raised panels; deep for inset data fields.
- **Shadow Strategy:** Use `shadow-z1` for ordinary lift and `shadow-z2` for raised or floating surfaces.
- **Border:** Usually none; use the translucent hairline only for controls and floating companion boundaries.
- **Internal Padding:** Most cards use `12px` to `14px`; dense metric blocks use `7px` to `11px`.

### Inputs / Fields
- **Style:** Deep background, translucent hairline border, `10px` corners, and compact `6px 10px` padding. Text uses Inter or JetBrains Mono depending on whether the value is a freeform identifier or a system datum.
- **Focus:** Border shifts to Instrument Lavender and the global amber focus outline remains visible.
- **Error / Disabled:** Errors use Danger Rose copy; disabled actions reduce opacity and keep the underlying surface role unchanged.

### Navigation
- **Style:** A compact horizontal pill row beneath the top bar. Active route uses Instrument Lavender with deep text and a tactile accent edge; inactive routes use Surface-2 with dim text. Status pills and Findings Pack provenance stay aligned at the far edge.
- **Responsive:** Preserve horizontal scan order; allow content rows to scroll or collapse rather than shrinking labels below legibility.

### Live Companion
A fixed, floating status surface at the lower-right corner keeps live guidance present without stealing the page. It uses a translucent Surface-2 background, a subtle hairline border, `10px` corners, monospace status text, and `shadow-z2`. It is hidden while idle.

### Checkboxes
Custom dark control (`.bl-check`): deep track, hairline border, `6px` corners; checked state fills Instrument Lavender with a deep check mark. The wrapping label carries the `24px` minimum hit area.

## Motion

Motion is a status instrument, never decoration. All motion is gated behind `prefers-reduced-motion: no-preference`.

- **Route enter** (`.rc-screen` keyframes): the authored moment — one `180ms` ease-out fade with a `5px` rise when a screen mounts. Nothing else on the page entrance-choreographs.
- **Live dot pulse** (`.bl-pulse`): a slow `2.4s` opacity breath on dots that mean "this connection is alive" (sidecar dot, connection pill, urgent champ-select timer). Never applied to static markers.
- **Bar easing** (`.bl-width`): `450ms` exponential ease-out on width for determinate fills (Backfill progress, benchmark bars, personal win-rate fill, matchup bars). Bars sit in fixed-height clipped tracks.
- **Urgent timer**: the champ-select timer pill flips from Instrument Lavender to Caution Amber at `≤30s` and takes the live-dot pulse; amber means "attend now" and nothing else uses it while live.

## Do's and Don'ts

### Do:
- **Do** keep the deep midnight canvas visible around tonal surface tiers.
- **Do** use JetBrains Mono for compact labels, champion names, percentages, and state readouts.
- **Do** reserve Instrument Lavender for the current route, selected role, and primary action.
- **Do** keep Findings Pack provenance visible when showing population numbers.
- **Do** use teal, blue, amber, and rose as semantic signals with restrained coverage.
- **Do** preserve the amber focus outline and minimum interactive target sizes.

### Don't:
- **Don't** use glossy esports spectacle, neon rainbow gradients, or decorative noise as a substitute for hierarchy.
- **Don't** present Findings Pack population values as if they were the user's Personal History.
- **Don't** turn every card into a raised or glowing surface; tonal layering is the default.
- **Don't** use imperative copy for Diagnostic findings; phrasing discipline belongs to product behavior as well as presentation.
- **Don't** render enemy summoner names in champ select UI or introduce enemy ability/ult timers.
