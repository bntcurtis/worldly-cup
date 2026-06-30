# WorldlyCup — Handoff Notes

Written for whoever (human or agent) picks this up next. Repo: https://github.com/bntcurtis/worldly-cup
(deployed via Cloudflare Pages from the pushed branch — static site, no build step).

## What this is

A WC2026 player-origins explorer + three browser games, built around one dataset: for each of
the 1,248 players at the tournament, where they were **born**, what they're **eligible** for
(citizenship, a proxy), who they **currently** represent, and every national team (senior +
youth) they've **ever** represented. The spark was noticing Morocco players who came up through
Dutch youth teams during a Netherlands–Morocco match.

It's a single-page static site (`index.html`, MapLibre GL JS via CDN, no build tooling — by
design, so the user can just push to GitHub and deploy via Cloudflare Pages) with four modes:
**Whose Team?** (guess a player's nation from clues), **Guess the Team** (guess a nation from
squad-level clues), **Birthplace Hunt** (click every birth country for a given squad), and
**Explore** (free browsing, de-emphasized in the nav — the games are the focus).

## Current state: working, two known issues outstanding

All three games and Explore are functional and were verified in a live preview over the course
of this session. The two open issues are below — **pin placement is the one the user
specifically asked to flag**, and is being handed to a different coding agent to finish.

---

## ⚠️ KNOWN ISSUE #1: Pin placement is still imprecise (read this first)

### Symptom
Birthplace markers (the "pegman" icons) generally land in the right *region* now but are not
pixel-accurate to their lng/lat — e.g. a pin for a player born in Clichy (a Paris suburb)
rendered visually closer to Spain than France before the latest fix, and the user reports
**placement issues persist** even after that fix.

### What's already been tried, in order
1. **Original bug:** markers floated far from their coordinates (e.g. over open ocean).
   Root cause: the marker's wrapper `<div>` had no explicit CSS width/height, so MapLibre's
   `translate(-50%, -50%)`-based anchor centered on the `<img>`'s **natural** pixel size
   (377×629 — see below) instead of its **rendered** CSS size (28×46), throwing the marker
   roughly half the image's natural width off target. **Fix:** gave `.peg` and `.peg img`
   explicit `width:28px;height:46px` (see `index.html` CSS, search `.peg{`). This was real and
   verified — markers stopped landing in open water.
2. **Second-order bug (still open):** even with correct sizing, the marker's *anchor point*
   (`anchor:'bottom-left'` in the `maplibregl.Marker` constructor, see `dropPin()` in
   `index.html`) assumes the pegman graphic's visual "tip" sits exactly at the bottom-left
   **corner** of its bounding box. **It doesn't.** Looking at the source art
   (`pegman-white.png`, 377×629px — also see `pegman-dark-grey.png` / `pegman-light-grey.png`,
   same dimensions), the figure stands on a gold teardrop/pin shape with a soccer ball
   overlapping its left side; the pointed tip of the teardrop is at the **bottom edge but
   inset from the left edge** — by rough visual estimate, somewhere around 15–20% of the
   image's width in from the left (not 0%), and right at the bottom (~100% of height). So
   `anchor:'bottom-left'` is closer than the original bug but still systematically off by
   roughly that inset amount, scaled to the rendered 28×46 size (~4–6px at the current render
   size, more at higher zoom since screen-pixel error is constant but represents more real-world
   distance at high zoom... actually the reverse — the *screen-pixel* error is constant
   regardless of zoom, so it's most visually obvious at high zoom / when comparing to small
   countries or precise landmarks, which is exactly what the user's Clichy screenshot showed).

### Recommended fix (pick one)
- **Option A — precise manual offset (no asset changes).** Switch the marker to
  `anchor:'center'` and add an explicit `offset:[x, y]` in CSS pixels, computed from the
  *actual* tip position in the source PNG, scaled to the rendered 28×46 size. To get this
  right, don't eyeball it from a screenshot like this handoff did — open `pegman-white.png` in
  an image editor (or write a tiny script that scans for the bottom-most non-transparent pixel
  column) to find the exact tip coordinate in the 377×629 source, then scale:
  `offsetX = (tipX_source/377 * 28) - 14` (14 = half of 28, since MapLibre's `offset` is
  relative to the anchor position which for `'center'` is the box center),
  `offsetY = (tipY_source/629 * 46) - 23`. Note MapLibre's `offset` sign convention — verify
  empirically (drop one marker on a known coordinate like the Vatican, zoom to max, and adjust
  sign/magnitude until the tip lines up exactly).
- **Option B — fix the asset instead (probably easier and more robust).** Re-export or pad the
  pegman PNGs (transparent padding is fine) so the visual tip sits **exactly at the bottom
  center** of the image bounds, then use MapLibre's built-in `anchor:'bottom'` (one of the 9
  standard keyword anchors — exact by construction, no manual offset to compute or maintain).
  This is more robust long-term since any future swap of the marker graphic won't silently
  reintroduce the offset bug. Given there are 3 pegman color variants, this means re-padding
  all 3 consistently.
- Whichever you pick, also recompute the **popup offset** — currently
  `new maplibregl.Popup({offset:[14,-44], ...})` in `dropPin()` is hand-tuned to match
  `anchor:'bottom-left'` and will look wrong (popup arrow not pointing at the pin) if the
  marker anchor changes without updating this too.

### How to verify the fix
Zoom to max zoom (`MAP.flyTo({center:[lng,lat], zoom:7})` or similar) on a player with a
precisely known birth city — e.g. search `app_data.json` for someone born in a small, visually
distinctive location (a capital city, an island nation) — and confirm the pin's tip sits exactly
on the coordinate, not just "in the right country." The Explore mode's `revealTeam()` function is
the fastest way to get a screenful of pins to check at once; Algeria and Cabo Verde (lots of
foreign-born players, spread across Europe) are good visual stress-tests since errors are easy to
spot when a "France" pin should be nowhere near "Spain."

> **⚠️ When choosing test players, skip anyone with `born_city_is_fallback: true` in
> `app_data.json`.** For ~39 players the real birth city is unknown, and `born_city`/`lat`/`lng`
> were deliberately, manually set to the player's country's **capital** as a placeholder (see
> Known Issue #3 below). Their pins are *correctly* sitting on the capital by design — that is
> not the bug you're looking for, and several of these players share identical coordinates
> (e.g. multiple South Korea players all "born in" Seoul), which is also expected, not a
> pin-clustering bug. Filter these out before picking verification test cases:
> `DATA.teams.flatMap(t=>t.players).filter(p=>!p.born_city_is_fallback && p.lat!=null)`.

### Where to look in the code
- `dropPin(p, group)` in `index.html` — creates the marker, sets `anchor:'bottom-left'`, sets
  the popup offset.
- `.peg`, `.peg img`, `.peg .badge` CSS rules (search `.peg{` in the `<style>` block) — the
  explicit sizing that fixed the *first* bug; don't remove this when fixing the anchor.
- `dropPin()` is called from three places: `revealTeam()` (Explore), `endRound()` (Whose Team?),
  `revealGuess()` (Guess the Team). Birthplace Hunt does **not** drop pins (it only shades
  countries) — fixing `dropPin()` once fixes pins everywhere they appear.

---

## ⚠️ KNOWN ISSUE #2: `players_worldcup2026.csv` and `app_data.json` now disagree on `born_in`

This isn't a bug in the live app (the app only reads `app_data.json`, which is correct) but is a
trap for anyone — including a future agent — who analyzes the CSV directly.

- `players_worldcup2026.csv`'s own `born_in` and `notes` columns come from Wikidata's `P17`
  (country) property on each birthplace, which is **wrong for colonial-history places** — e.g.
  it lists *France* as the country for several Algerian cities because France historically
  administered Algeria, and the country-extraction logic in `build_dataset.py` (in the original
  pipeline) didn't filter this out for every case.
- `build_appdata.py` (the script that produces `app_data.json`, what the live app actually
  reads) **independently re-derives `born_in` from each player's `born_lat`/`born_lng` via
  point-in-polygon** against `countries_50m.geojson`. This is correct — e.g. it correctly shows
  Algeria as 16/26 born abroad, not the CSV-implied 25/26.
- **The CSV itself was never patched to fix this.** If you regenerate stats, do further data
  analysis, or build new features directly from `players_worldcup2026.csv`'s `born_in` field,
  you'll reproduce the colonial-history bug. Always derive birth country from
  `born_lat`/`born_lng` via coordinate lookup (copy the point-in-polygon logic from
  `build_appdata.py`), not from the CSV's `born_in` column.

### `build_dataset.py` is now DEPRECATED — it has a runtime guard, don't bypass it lightly
**The CSV's data pipeline changed hands.** Outside of this codebase, the user ran a separate
validation pass (a different agent + manual review) directly against `players_worldcup2026.csv`:
- 68 rows now have `match_source = web-verified`, a value `build_dataset.py` never writes (it
  only writes `wikidata-name+dob` or `wikipedia-squad`) — these are hand-corrected.
- 39 rows now have `needs_review = fallback` — see **Known Issue #3** below, a separate, newer
  finding.
- `needs_review` is empty/`NO` for everything else; confidence is 1,227/1,248 `high`.

`build_dataset.py` itself only ever wrote to **`players_enriched.csv`**, a separate file — it
never touched `players_worldcup2026.csv` directly. The actual danger was the *manual workflow*
established during development: run the script, review the output, then
`cp players_enriched.csv players_worldcup2026.csv`. That copy step is now destructive — it would
erase all the hand-validation above, since the script has no concept of `web-verified` or
`fallback` rows. **A runtime guard was added** (top of `build_dataset.py`'s `if __name__`
block): running `python3 build_dataset.py` now exits immediately with an explanatory error
unless you pass `--force`. The big comment at the top of the file explains the same thing. If
you ever need to regenerate data (e.g. a roster swap before the tournament), regenerate into
`players_enriched.csv` as before, then manually merge only the specific changed rows into
`players_worldcup2026.csv` by hand — never copy the whole file over.

### Practical workflow if you touch the CSV
1. Edit `players_worldcup2026.csv` directly (by hand, or by merging in specific rows — see
   above). Do not run `build_dataset.py` over it.
2. **Always re-run `python3 build_appdata.py` afterward** to regenerate `app_data.json` — the
   live app won't see CSV changes otherwise. This has already been done once as part of this
   handoff (in response to the CSV update that introduced the `fallback` rows — see Known Issue
   #3) — `app_data.json` is current as of this handoff. Keep doing this every time the CSV changes.

---

## ⚠️ KNOWN ISSUE #3: ~39 players have a fabricated/placeholder birth city (capital-city fallback)

**This is newer than Known Issue #2 and affects gameplay, not just data hygiene.**

For 39 players, nobody could determine the real birth city, so **`born_city`, `born_lat`, and
`born_lng` were manually set to the player's *country's capital city*** as a placeholder
(`needs_review = "fallback"` in the CSV). `born_in` (the country) is still trusted for these
rows — only the specific city/coordinates are fabricated. Examples: several South Korea players
all show `born_city = "Seoul"` at identical coordinates; Egypt players show `born_city = "Cairo"`;
Qatar players show `born_city = "Doha"`. This is plumbed through to `app_data.json` as a new
boolean field on each player record: **`born_city_is_fallback: true`** (added to
`build_appdata.py` as part of this handoff — read its inline comment there for the exact
rationale).

**The user explicitly does not trust this data to be shown as a specific clue or fact**,
particularly in **Whose Team?**, whose `buildClues()` function (in `index.html`, search
`function buildClues`) currently does exactly that — its first clue is always:
```js
c.push(['Born in', `${p.born_city?p.born_city+', ':''}${p.born_in}`], ...)
```
For a fallback player, this clue currently renders as e.g. **"Born in Seoul, South Korea"** when
the player almost certainly wasn't born in Seoul — it's a guess. This is a real, live
misleading-clue bug, not just a data-quality footnote, and the user asked that it be fixed by
**this CSV's next caretaker** (it was reported too late in this session to fix here).

**Where this also shows up, beyond the obvious clue:**
- `dropPin()`'s popup HTML (`index.html`, search `born_city||''`) shows the city name in every
  pin's popup — same problem, lower stakes (a popup is more obviously "a label," not phrased as
  a guessing clue), but still worth flagging/styling differently if you have time.
- Birthplace Hunt and Guess the Team don't use `born_city` in clues today, so they're unaffected
  — only Whose Team?'s "Born in" clue is the urgent one.

**Suggested fix:** in `buildClues()`, when `p.born_city_is_fallback` is true, either drop the
city from that clue entirely (fall back to country-only: `"Born in South Korea"`, which is still
true and still useful as a clue) or visibly caveat it. Country-only is probably the better
default — it keeps the clue honest without losing it as a difficulty signal. Re-run
`build_appdata.py` is **not** needed for this fix; the flag is already in the current
`app_data.json` — this is purely an `index.html` JS change.

---

## Architecture notes / key decisions (so you don't relitigate them)

- **No build step, on purpose.** `index.html` is a single file loading MapLibre GL JS from a
  CDN; `app_data.json` and `countries_50m.geojson` are static fetches. The user wanted to push
  straight to GitHub and deploy via Cloudflare Pages with zero tooling, given the World Cup ends
  in a few weeks and the priority was sharing it with friends quickly, not engineering for the
  long term.
- **Country highlighting uses a dedicated GeoJSON source/layer (`hi` / `hi-fill` / `hi-line`),
  not MapLibre `feature-state`.** Feature-state fill expressions were tried first and **did not
  visually render** in this environment despite the state being readable via
  `getFeatureState()` — a real, verified-reproducible MapLibre quirk in this setup, not a typo.
  The working pattern: maintain a plain JS object `HI = {iso: 'kind'}`, call `renderHi()` to
  rebuild a small FeatureCollection from it and `setData()` it into the `hi` source. Don't
  switch back to feature-state without re-verifying it actually paints pixels (a `getFeatureState`
  check alone is not sufficient proof — screenshot it).
- **Country labels are an opt-in hover tooltip** (`#tt` div, toggled by the "Country names"
  button, default **off**), not always-on map labels. The original always-on label layer
  rendered one label per *polygon ring*, so islands and multi-part countries (Canada, Greenland,
  Antarctica) showed duplicate labels scattered across the map. Hover tooltips sidestep this
  entirely and double as the user's requested "easy mode" toggle.
- **`repPoint()` / `countryPoint()`** compute a representative centroid point per country
  (largest polygon ring's vertex average) for two purposes: (a) labels, one per country, and
  (b) framing map reveals. Framing reveals with a country's **polygon bounding box** was tried
  first and broke for the USA/Russia (their polygons cross the antimeridian, so the bbox spans
  the whole globe) — framing with points instead (birthplace coordinates + this representative
  point) fixed it.
- **`born_in` is coordinate-derived in `build_appdata.py`, not taken from the CSV** — see Known
  Issue #2 above for why.
- **The 48 competing nations get a visible "team" highlight color** during Whose Team? and Guess
  the Team so the click target is obvious; wrong guesses get an explicit text message (not just
  a color flash) after the user reported that color-only feedback was easy to miss.
- **Daily puzzle was explicitly declined by the user** — don't add one. ("World Cup will be over
  in a few weeks, I just want to share this with friends and let them enjoy it now.")
- **Dad-joke / soccer-pun motif is intentional but the user has not finalized it** — "Misses"
  instead of strikes, "⚽ Assist: how many?" instead of hint, "Back of the net!" / "Full time!" /
  "clean sheet!" / "Final whistle" for game outcomes. The user said they'll make a final call on
  these later; don't assume they're locked in, but don't strip them preemptively either.
- **Logo/favicon is `logo.png`** (a 128px resize of `globe-ball2.png`, made via macOS `sips`),
  chosen over `globe-ball1.png` (softer cartoon, fights the dark theme) and `globe-ball3.png`
  (great detail, too busy to read as a small icon). `globe-ball3.png` could work well as a large
  hero/share image if one is ever added.
- **Nav is games-first.** The three games are the primary tabs; Explore is a smaller, muted
  "Explore ↗" link on the far right. The app opens directly into a Whose Team? round
  (`mode` defaults to `'game'`, `newRound()` is called at the end of the map's `load` handler) —
  Explore is reachable but is no longer the landing experience.

## Environment quirks (if you're using a similar preview/dev setup)

- `countries_50m.geojson` is ~3MB; in this session's preview environment it reliably took
  **10–15 seconds** to load and fire MapLibre's `load` event. Don't conclude the map is broken
  if `MAP.isStyleLoaded()` is `false` immediately after a reload — wait and poll.
  `countries_50m.geojson` was deliberately chosen over the lighter 110m Natural Earth dataset
  because the 110m set is missing Curaçao, a competing nation.
- The preview iframe in this session occasionally "wedged" after many reloads / `setStyle()`
  calls — a fresh minimal MapLibre map would stop firing its `load` event with no error at all.
  Fix was to fully stop and restart the preview server, not just reload the page.
- `app_data.json` is fetched with a `?v=timestamp` cache-buster in `init()` because the local
  `http.server` was observed serving a stale cached copy after edits.
- Local dev server: `.claude/launch.json` defines a `worldlycup` config
  (`python3 -m http.server 8848`).

## File manifest

| File | Role |
|---|---|
| `index.html` | The entire app (~590 lines): map setup, all 4 modes, game logic, styling. |
| `app_data.json` | Game-ready data layer the app fetches at runtime. Generated by `build_appdata.py`. **Regenerate after any CSV edit.** Current as of this handoff (includes `born_city_is_fallback`). |
| `build_appdata.py` | CSV → `app_data.json`. Coordinate-based `born_in` derivation (point-in-polygon) lives here, plus the `born_city_is_fallback` flag (see Known Issue #3). This is the **only** script you should run going forward. |
| `players_worldcup2026.csv` | The underlying player dataset, 1,248 rows, **now hand-maintained** (not purely pipeline-generated). See Known Issues #2 and #3 before trusting `born_in` or `born_city`. |
| `build_dataset.py` | **Deprecated**, reference only. Roster → `players_enriched.csv` via Wikidata + Wikipedia. Has a runtime guard (`--force` required) since re-running it and copying its output over the live CSV would erase hand-validation — see Known Issue #2. |
| `countries_50m.geojson` | Natural Earth 50m country polygons (242 features, incl. Curaçao). |
| `teams.csv` | Team metadata (group, confederation, FIFA code) — feeds `build_appdata.py`. |
| `logo.png` | App logo / favicon (resized `globe-ball2.png`). |
| `globe-ball1/2/3.png` | Logo candidates the user supplied; `2` was chosen, `1`/`3` unused but kept. |
| `pegman-white/dark-grey/light-grey.png` | Birthplace marker art the user supplied; `white` is currently used. All 3 share the pin-placement issue above. |
| `README.md` | Dataset-focused documentation (columns, method, data-quality caveats). Updated this session to match current numbers — see the CSV-vs-app_data warning box near the top. |
| `HANDOFF.md` | This file. |

## Suggested next steps, roughly in priority order

1. Fix pin placement (Known Issue #1) — this is the one the user is actively waiting on. Remember
   to exclude `born_city_is_fallback` players from your test cases (see the callout in #1).
2. Fix the Whose Team? "Born in" clue for fallback players (Known Issue #3) — small, contained
   JS change in `buildClues()`, no data regeneration needed, but it's a live misleading-clue bug.
3. Be aware of Known Issue #2 (CSV `born_in` vs. `app_data.json` `born_in` divergence) if you do
   any further data work — don't reintroduce it.
4. User will make a final call on the soccer-pun copy — be ready to adjust tone up or down.
5. Nothing else is currently blocking; the 4 modes are feature-complete and were working as of
   this handoff.
