# AGENT CLARIFICATION — aad0ca35fc6cd101a
## Date: 2026-06-02
## Priority: STOP current task and re-read this in full

---

IMPORTANT CORRECTION — the user has clarified what they want. Stop the IEBC expert panel approach and focus on these UI problems:

### Problem 1 — Gold/yellow topbar title still showing on LF pages

The `.lf-fullpage` class sets `visibility:hidden` on `#main.lf-fullpage .tb-title` (line ~13993 in eagleeye.html) but it may not be working reliably.

**Root cause to investigate:** `nav()` sets the class on both `.content` AND `#main` — but the CSS rule targets `#main.lf-fullpage .tb-title`. Verify that `#main` actually gets the class (not just `.content`), and that `.tb-title` is actually a **descendant** of `#main` in the DOM. If the topbar/title bar sits outside `#main`, the CSS selector will never match.

Also check: does `visibility:hidden` leave a gap? Should it be `display:none` instead?

---

### Problem 2 — Full-page layout NOT being applied

The LF hero banners should bleed edge-to-edge with zero padding and no gap at the top. Currently the layout looks broken/padded.

**Root cause to investigate:**
- `.content.lf-fullpage { padding:0; }` — is `.content` getting the class? (nav() does toggle it on `.content` at line 3615)
- `.content.lf-fullpage .lf-hero { border-radius:0; margin-bottom:0; padding:28px 32px; }` — is this taking effect?
- Is there a `padding-top` on `.content` from the topbar height that overrides the padding:0?
- Check if `.lf-wrap { padding:28px 32px 80px }` is overriding `.content.lf-fullpage .lf-wrap { padding:0 0 80px }`

---

### Problem 3 — Missing pages: Medical Courier and Cargo Van tabs

- `nav('lf-medical')` is wired in the sidebar (line 771) but there is NO `<div id="page-lf-medical">` page in the HTML
- There is no `nav('lf-cargo-van')` or Cargo Van tab at all yet

**Action required:** Create both `lf-medical` and `lf-cargo-van` pages with full-page layouts matching the existing 4 LF pages (NEMT, Executive, Courier, Gig). Use the same structure:
```
lf-wrap > lf-hero > lf-kpis > lf-actions > lf-table-wrap
```

Add them to `_lfFullPages` array, `pageNames`, the sidebar nav, and `loadLightFleet()` call in `nav()`.

Color suggestions:
- Medical Courier: `rgba(239,68,68,...)` red theme, class `lf-hero-medcour`
- Cargo Van: `rgba(249,115,22,...)` orange theme, class `lf-hero-cargo`

---

### Problem 4 — ALL LF pages need consistent, polished UI

All LF pages (NEMT, Executive, Courier, Gig, Medical Courier, Cargo Van) must:

1. **Properly hide the gold topbar title** — fix the CSS selector so it actually works
2. **Hero banner bleeding edge-to-edge** — fix padding/margin so hero starts at top with no gap
3. **Consistent layout:** hero → KPI bar → filter bar → table/content
4. **Polished appearance** — not broken, not padded, professional

---

### How to investigate

Read the current eagleeye.html focusing on:
- Lines ~107-120: `.tb-title` definition and its position in DOM relative to `#main`
- Lines ~820-840: the topbar HTML structure — is `.tb-title` inside `#main`?
- Lines ~13949-14020: all the `.lf-*` CSS
- Lines ~3603-3656: the full `nav()` function
- Lines ~14050-14250: the existing 4 LF page HTML blocks

Fix the CSS/HTML so all 4 existing LF pages look correct, then add the 2 missing pages in the same style.

---

### What NOT to do

- Do NOT build IEBC expert panels
- Do NOT add AI chat panels to LF pages
- Do NOT call `lfRunExpert()` for the new pages unless the user specifically asks
- Focus ONLY on the layout/UI fixes described above
