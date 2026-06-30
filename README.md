# World Cup 2026 — Player Origins Dataset

Where every player at the 2026 men's World Cup was **born** (down to city + coordinates),
who they're **eligible** for, who they **currently** represent, and every national team
they've **ever** played for (senior + youth). Built to explore the tournament's diaspora /
allegiance-switch stories (e.g. Morocco players who came up through Dutch and French youth
systems).

## Files
- **`players_worldcup2026.csv`** — the dataset, 1,248 players (48 teams × 26).
- **`build_dataset.py`** — the reproducible pipeline. `python3 build_dataset.py`
  (Python 3, stdlib only; needs internet). Caches all Wikidata/Wikipedia responses under
  `cache/`, so re-runs are fast and resumable. Delete `cache/entities.json` to force a
  clean re-fetch.

## Columns
| column | meaning |
|---|---|
| `player_name`, `date_of_birth`, `position`, `club_team`, `caps` | from the base roster |
| `currently_playing_for` | country represented at WC2026 (authoritative, from the squad list) |
| `born_in` | country of birthplace (present-day country) |
| `born_city` | birthplace city/place label |
| `born_lat`, `born_lng` | birthplace coordinates (for map pins) |
| `qualified_for_proxy_citizenship` | countries of citizenship — **a proxy** for eligibility (see caveat) |
| `ever_senior_national_team` | every senior national team capped for (`;`-separated) |
| `ever_youth_national_team` | every youth national team, with level, e.g. `Netherlands (U-15)` |
| `wikidata_qid` | matched Wikidata entity (for auditing / further enrichment) |
| `match_confidence` | `high` / `low` / `unmatched` |
| `match_source` | how the player was matched: `wikidata-name+dob` or `wikipedia-squad` |
| `needs_review` | `YES` where a human should verify |
| `notes` | why flagged + interesting tags (`born abroad`, `possible switch`, …) |

## How it was built
1. **Base roster** from the open [FIFA WC2026 dataset](https://github.com/mominullptr/FIFA-World-Cup-2026-Dataset)
   (names, DOB, club, caps). It has *none* of the origin columns — those are derived here.
2. **Match to Wikidata** by name search, disambiguated by **exact date of birth** +
   footballer occupation, with shortened/reversed name variants for full-birth-name and
   name-order mismatches.
3. **Wikipedia fallback** for everyone the name search missed: harvest every player linked
   from the *2026 FIFA World Cup squads* Wikipedia page, resolve their articles to Wikidata
   QIDs, and join back to the roster **by date of birth** (+ nationality on DOB collisions).
   This is spelling-independent, so it rescues romanization mismatches (Arabic, Korean name
   order) and even mangled source names (e.g. "MARQUINHOSMarcos" → Marquinhos).
4. **Derive columns** from Wikidata properties: birthplace (P19) → city label, coordinates
   (P625), and present-day country (P17, filtering out defunct states via P31); citizenship
   (P27); national-team memberships (P54) split into senior vs youth by parsing team labels.
5. **Normalize** country names so the roster and Wikidata agree (Czechia/Czech Republic,
   USA/United States, IR Iran/Iran, Côte d'Ivoire/Ivory Coast, Türkiye/Turkey, etc.).

## Data quality (current build)
- **1,227 / 1,248 (98%) high-confidence.** 0 rows currently flagged `needs_review` — the
  remaining low/medium-confidence rows (21 total) were since hand-verified outside the
  pipeline (see `match_source = web-verified`) and no longer need attention.
- **1,227+ players have birthplace coordinates.**

> **⚠️ CSV vs. app_data.json — two slightly different pictures, read before trusting either:**
> `players_worldcup2026.csv`'s own `born_in` / `notes` columns come straight from Wikidata's
> P17 (country) property, which is **wrong for colonial-history birthplaces** — e.g. it lists
> *France* as the country for cities in Algeria because France historically administered
> Algeria. **`build_appdata.py` independently re-derives `born_in` from each player's
> `born_lat`/`born_lng` via point-in-polygon against `countries_50m.geojson`**, which is
> correct (Algeria is 16/26 born abroad, not the CSV-implied 25/26). The live app reads only
> `app_data.json`, so it shows the correct numbers — but **any one-off analysis run directly
> against the CSV's `born_in` column will reproduce the colonial-history bug.** Always derive
> birth country from coordinates, not the CSV's `born_in` field. See "Known issues" in
> `HANDOFF.md` for the full story.

### Known limitations
- **`qualified_for_proxy_citizenship` is a *proxy*, not ground truth.** FIFA eligibility
  also covers grandparents and 5-year residency, which no public database fully captures.
- **Youth-cap coverage varies** — well documented for prominent players, patchy for others.
- A handful of birthplaces resolve only to a country (no city), so their coordinates are a
  country centroid rather than a precise point.
- **Pin placement on the map has known issues** — see `HANDOFF.md`.

## Notable findings
(numbers below are from `app_data.json`, i.e. coordinate-corrected — see warning above)
- **Most foreign-born squads**: Curaçao 24/26, Congo DR 20/26, Morocco 18/26, Haiti 17/26,
  Algeria & Bosnia and Herzegovina 16/26.
- **Allegiance switchers** (youth for one nation, now another): Brahim Díaz (Spain→Morocco),
  Sead Kolašinac (Germany→Bosnia), Bilal El Khannouss (Belgium→Morocco), Sofyan Amrabat
  (Netherlands→Morocco), and many others (124 total players with some prior allegiance,
  per `app_data.json` team stats).

## Source & licensing
Derived from Wikidata (CC0), English Wikipedia (CC BY-SA), and the community FIFA WC2026
roster dataset. Verify the `needs_review` rows before any published/competitive use.
