# ChakraOps Design System

**Version:** 1.0  
**Purpose:** Premium fintech-grade UI for ChakraOps trading operations console.

---

## 1. Theme System

### Modes

| Mode   | Use case                 | Default |
|--------|---------------------------|---------|
| **Dark**   | Primary; operator consoles, low-light trading | Yes     |
| **Light**  | Secondary; reports, print-friendly views      | No      |
| **System** | Follow OS preference                           | Optional |

### Implementation

- **Toggle:** `dark` / `light` class on `<html>`
- **Tailwind:** `darkMode: ['class']`
- **System:** Use `prefers-color-scheme: dark` when mode is `system`; apply `dark` or `light` accordingly
- **Storage:** Persist preference in `localStorage` key `chakraops-theme` (`"dark"` | `"light"` | `"system"`)

### Tailwind Config

```js
// tailwind.config.js
export default {
  darkMode: ['class'],
  theme: {
    extend: {
      // Theme variables for dark/light
    },
  },
}
```

### CSS Variables (optional)

```css
:root {
  --chakraops-bg-primary: hsl(0 0% 4%);
  --chakraops-bg-secondary: hsl(0 0% 7%);
  --chakraops-border: hsl(0 0% 14%);
}

.dark { /* dark overrides */ }
.light { /* light overrides */ }
```

---

## 2. Typography

### Font

- **Primary:** Inter (Google Fonts)
- **Mono:** `font-mono` (system-ui monospace, e.g. ui-monospace)

**Import (index.html):**

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
```

### Type Scale

| Token        | Size   | Weight  | Use                    |
|-------------|--------|---------|------------------------|
| `text-xs`   | 12px   | 400–600 | Labels, captions, metadata |
| `text-sm`   | 14px   | 400–600 | Body, table cells      |
| `text-base` | 16px   | 400–600 | Main body              |
| `text-lg`   | 18px   | 600     | Section titles         |
| `text-xl`   | 20px   | 700     | Page titles, verdicts  |
| `text-2xl`  | 24px   | 700     | Scores, hero numbers   |

### Hierarchy

- **Page title:** `text-xl font-bold`
- **Section title:** `text-xs font-semibold uppercase tracking-wide text-zinc-500`
- **Card title:** `text-sm font-semibold`
- **Label:** `text-xs text-zinc-500` (block)
- **Data value:** `font-mono text-zinc-200` or `text-zinc-300`
- **Muted:** `text-zinc-400` or `text-zinc-500`

### Numeric Precision

- **Prices, scores, IDs:** `font-mono`
- **Monospace:** Use for strike, delta, expiry, credit, max_loss, DTE, etc.
- **Alignment:** Right-align numeric columns in tables

---

## 3. Color Tokens

### Dark Theme (Primary)

| Token               | Tailwind                   | Hex (approx) | Use                        |
|---------------------|----------------------------|--------------|----------------------------|
| Background primary  | `bg-zinc-950`              | #0a0a0a      | Page, sidebar              |
| Background secondary| `bg-zinc-900`              | #171717      | Cards, panels              |
| Card background     | `bg-zinc-900/50`           | rgba(23,23,23,0.5) | Card surfaces       |
| Border              | `border-zinc-800`          | #27272a      | Cards, tables, inputs      |
| Text primary        | `text-zinc-100` / `text-white` | #fafafa  | Headings, key values       |
| Text muted          | `text-zinc-400` / `text-zinc-500` | #a1a1aa | Labels, secondary text     |
| Success             | `text-emerald-400`         | #34d399      | ELIGIBLE, OK, PASS         |
| Warning             | `text-amber-400`           | #fbbf24      | HOLD, WARN, FAIL           |
| Danger              | `text-red-400`             | #f87171      | BLOCKED, DOWN, ERROR       |
| Neutral             | `text-zinc-400`            | #a1a1aa      | Unknown, N/A               |

### Light Theme (Secondary)

| Token               | Tailwind                   | Use                        |
|---------------------|----------------------------|----------------------------|
| Background primary  | `bg-zinc-50`               | Page                       |
| Background secondary| `bg-white`                 | Cards                      |
| Card background     | `bg-zinc-100/50`           | Card surfaces              |
| Border              | `border-zinc-200`          | Dividers                   |
| Text primary        | `text-zinc-900`            | Headings                   |
| Text muted          | `text-zinc-500`            | Labels                     |
| Success             | `text-emerald-600`         | ELIGIBLE, OK               |
| Warning             | `text-amber-600`           | HOLD, WARN                 |
| Danger              | `text-red-600`             | BLOCKED, DOWN              |

### Status Palette

| Status   | Background           | Text               |
|----------|----------------------|--------------------|
| OK/PASS  | `bg-emerald-500/20`  | `text-emerald-400` |
| WARN/FAIL| `bg-amber-500/20`    | `text-amber-400`   |
| BLOCKED/DOWN | `bg-red-500/20` | `text-red-400`     |
| Neutral  | `bg-zinc-500/20`     | `text-zinc-400`    |

---

## 4. Component Guidelines

### Card

- **Container:** `rounded border border-zinc-800 bg-zinc-900/50 p-3`
- **Padding:** `p-3` (12px)
- **Title:** `mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500`
- **Dense:** `p-2` for compact layouts

### Badge

- **Base:** `inline-flex rounded border px-2 py-0.5 text-xs font-medium`
- **Band A:** `border-emerald-500/50 bg-emerald-500/10 text-emerald-400`
- **Band B:** `border-amber-500/50 bg-amber-500/10 text-amber-400`
- **Band C:** `border-zinc-500/50 bg-zinc-500/10 text-zinc-400`

### Status Badge

- **Base:** `inline-flex rounded px-1.5 py-0.5 text-xs font-medium`
- **Success:** `bg-emerald-500/20 text-emerald-400` (OK, PASS, ELIGIBLE)
- **Warning:** `bg-amber-500/20 text-amber-400` (WARN, FAIL, HOLD)
- **Danger:** `bg-red-500/20 text-red-400` (BLOCKED, DOWN)
- **Neutral:** `bg-zinc-500/20 text-zinc-400` (—, UNKNOWN)

### Table

- **Container:** `overflow-x-auto rounded border border-zinc-800`
- **Base:** `w-full text-sm`
- **Header:** `border-b border-zinc-700 text-left text-zinc-500`
- **Cell:** `py-2 pr-2 px-3`
- **Row:** `border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30`
- **Zebra:** `odd:bg-zinc-900/30` on `<tr>`
- **Mono cells:** `font-mono` for numeric columns

### Button

- **Primary:** `rounded border border-zinc-600 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700`
- **Secondary:** `rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-800`
- **Disabled:** `disabled:opacity-50 disabled:cursor-not-allowed`
- **Compact:** `px-2 py-1 text-xs`

### Tooltip

- **Container:** `absolute z-50 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-200 shadow-lg`
- **Trigger:** Use `title` for native tooltip, or Radix UI Tooltip for custom
- **Delay:** 200–300ms
- **Max width:** 240px

### Icon Usage

- **Library:** Lucide React
- **Sizes:** `h-4 w-4` (16px) standard, `h-5 w-5` for emphasis
- **Color:** Inherit from parent; use `text-zinc-500` for muted, `text-emerald-400` for success
- **With label:** `flex items-center gap-2`
- **Standalone:** Add `aria-hidden="true"` when decorative

### Sidebar

- **Width:** `w-48` (192px)
- **Background:** `bg-zinc-950 border-r border-zinc-800`
- **Nav item:** `flex items-center gap-2 rounded px-2 py-1.5 text-sm`
- **Active:** `bg-zinc-800 text-white`
- **Inactive:** `text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200`
- **Icon:** `h-4 w-4 shrink-0`

---

## 5. Accessibility

### Contrast Ratio

- **Normal text:** ≥ 4.5:1 (WCAG AA)
- **Large text (≥18px or 14px bold):** ≥ 3:1
- **UI components:** ≥ 3:1
- **Verify:** `zinc-400` on `zinc-950` ≈ 6.5:1; `emerald-400` on `zinc-950` ≈ 5:1

### Minimum Font Sizes

- **Body:** 14px (`text-sm`)
- **Labels:** 12px (`text-xs`)
- **Minimum touch target:** 44×44px for interactive elements

### Focus States

- **Outline:** `focus:outline-none focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2 focus:ring-offset-zinc-950`
- **Visible:** All interactive elements must show clear focus
- **Skip link:** Provide "Skip to main content" for keyboard users

### Additional

- **Labels:** Associate labels with inputs via `htmlFor` / `id`
- **Tables:** Use `<th scope="col">` for column headers
- **Status:** Use `aria-live="polite"` for dynamic status updates
- **Reduced motion:** Respect `prefers-reduced-motion: reduce` (avoid animations for critical UI)

---

## 6. Layout

- **Main content:** `flex-1 overflow-auto p-4`
- **Grid:** `grid grid-cols-1 lg:grid-cols-2` or `lg:grid-cols-3` for responsive columns
- **Gap:** `gap-3` (12px) for sections; `gap-2` for dense grids
- **Max width:** No hard max for console; full viewport use
- **Spacing scale:** 2, 3, 4, 6 (8px, 12px, 16px, 24px)

---

## 7. Implementation Checklist

- [ ] Add theme toggle (dark / light / system)
- [ ] Persist theme in localStorage
- [ ] Apply Inter font globally
- [ ] Define CSS variables for color tokens (optional)
- [ ] Standardize StatusBadge against design system
- [ ] Add focus styles to all interactive elements
- [ ] Verify contrast for text/background pairs
- [ ] Document component usage in Storybook (optional)
