# Main Workspace — Desert Rose Cinematic Atelier

> **Project:** AutoCut Studio
> **Sources:** Anthropic `frontend-design` and `theme-factory` Skills
> **Selected theme:** Desert Rose
> **Platform:** Native Windows / PySide6

This page override supersedes the older dark OLED workspace and the generated
web-oriented master file. It is the approved visual direction for V3.3.

## Visual direction

- Editorial creative studio rather than a generic dashboard or settings form.
- Deep burgundy `#5D2E46` establishes the application chrome and primary action.
- Clay `#B87D6D` marks active media, timeline progress and secondary actions.
- Sand `#E8D5C4`, warm porcelain `#FAF7F4` and white create the working surfaces.
- Dusty rose `#D4A5A5` is reserved for selection/focus context; sage `#33725C`
  communicates ready/success with an accompanying text label.
- UI text uses local Segoe UI Variable / Microsoft YaHei UI fallbacks. No online
  font or runtime design dependency is introduced.

## Information architecture

```text
┌ deep-burgundy app header · brand · mode · local environment ┐
├ project library ┬ cinematic preview stage ┬ export inspector ┤
│ batch queue     │ 9:16 preview            │ base / brand /   │
│ source controls│ playback + timeline      │ visual / tools   │
├─────────────────┴─────────────────────────┴──────────────────┤
│ current task · progress · logs · cancel · primary render     │
└──────────────────────────────────────────────────────────────┘
```

- The preview stage and frame-accurate video/audio timeline are the single bold
  visual idea; surrounding panels remain quiet and utilitarian.
- Batch mode uses the left project queue; manual mode exposes the sortable source
  list in the same place without changing the overall workspace.
- The inspector groups the long settings model into independently scrollable tabs.
- The fixed task bar never overlaps pane content and keeps cancellation visible.

## Component rules

- Use the 8 px rhythm; 12–14 px pane margins; 7–11 px radii based on hierarchy.
- Prefer tonal grouping and sparse separators to nested cards.
- Keep one solid burgundy primary action. Clay is never used for a competing CTA.
- The preview uses a 9:16 surface and shrinks at the 900×650 minimum window.
- Inputs always retain visible labels; placeholders only provide examples.
- Drag-and-drop ordering retains add/delete/up/down keyboard alternatives.
- Focus uses a 2 px plum ring. Status is never communicated by color alone.

## Accessibility and behavior

- Normal text pairs meet WCAG 2.1 AA contrast; focus and brand boundaries meet
  3:1 non-text contrast.
- All long panes scroll vertically with horizontal scrolling disabled.
- Native checkbox indicators, keyboard focus and readable disabled states remain.
- The custom timeline is presentation-only; the source list continues to be the
  authoritative order and FFmpeg work remains outside the UI thread.
- No decorative animation, autoplay, network asset loading or online API.
