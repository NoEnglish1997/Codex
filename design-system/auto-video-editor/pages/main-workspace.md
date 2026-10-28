# Main Workspace — PySide6 Desktop Override

> **Project:** Auto Video Editor
> **Source:** UI UX Pro Max exact product match “Short Video Editor” plus WPF overflow guidance
> **Design dials:** variance 5/10, motion 2/10, density 8/10

This page override takes precedence over `../MASTER.md`. The generated master is
kept as the project-wide search result; the rules below adapt the verified product
match to a native Windows/PySide6 editor rather than a marketing page.

## Visual direction

- Style: Dark Mode (OLED), flat and technical; no decorative gradients or shadows.
- Background `#0B1120`; surface `#141C2E`; raised surface `#192134`.
- Primary editing/focus color `#EC4899`; sole primary CTA color `#2563EB`.
- Primary text `#F8FAFC`; secondary text `#A7B2C5`; border `#2A354A`.
- Destructive actions use red plus an explicit text label; status never relies on
  color alone.
- Use local Windows fonts only: Segoe UI Variable with Microsoft YaHei UI fallback.

## Information architecture

1. Compact top application bar for identity and persistent capability chips.
2. Adaptive desktop sidebar for four destinations: project, editing, preview,
   environment.
3. One independently scrollable content page; never nest a second content scroll
   region inside it.
4. Fixed task controller below the workspace with one blue primary action, explicit
   cancel/retry actions, progress, stage text and a collapsible diagnostic log.
5. The preview destination is unavailable in batch mode and visible in manual mode.

## Components and spacing

- Dense 4/8 px rhythm: 8 px control gaps, 12–16 px panel padding, 10–12 px section gaps.
- Corner radius: 6 px controls, 8–9 px panels; no random elevation scale.
- Visible labels remain next to every field; placeholders are examples, not labels.
- Focus uses a 2 px pink ring; disabled controls keep readable labels but lower
  emphasis.
- Native checkbox glyphs are retained so checked state is not communicated by color
  alone.
- Drag operations retain visible button alternatives (move up/down and numeric
  positioning).

## Interaction and accessibility

- Sidebar is keyboard navigable and reading order matches its visual order.
- The task process always exposes stage text and determinate progress when available.
- Long forms use a scroll area so keyboard focus cannot be clipped by the fixed task
  controller.
- No autoplay, decorative motion, emoji icons or network-loaded fonts/assets.
- Heavy FFmpeg work remains outside the UI thread; disabled states prevent duplicate
  task submission.
