#!/usr/bin/env python3
"""Transform players_worldcup2026.csv into app_data.json — the game-ready data layer
shared by both games and the explore/reveal view."""
import csv, json, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = list(csv.DictReader(open(os.path.join(HERE, "players_worldcup2026.csv"))))

# optional team metadata (group / confederation / fifa code) if teams.csv is present
TEAM_META = {}
tcsv = os.path.join(HERE, "teams.csv")
if os.path.exists(tcsv):
    for t in csv.DictReader(open(tcsv)):
        TEAM_META[t["team_name"]] = {
            "fifa_code": t.get("fifa_code", ""),
            "group": t.get("group_letter", ""),
            "confederation": t.get("confederation", ""),
        }

def parse_nats(field):
    """'Netherlands (U-15); Morocco (U-17)' -> {'Netherlands','Morocco'}"""
    out = set()
    for part in field.split(";"):
        part = part.strip()
        if part:
            out.add(part.split(" (")[0].strip())
    return out

teams = defaultdict(lambda: {"players": [], "name": None})
for r in ROWS:
    cur = r["currently_playing_for"]
    t = teams[cur]
    t["name"] = cur
    youth = parse_nats(r["ever_youth_national_team"])
    senior = parse_nats(r["ever_senior_national_team"])
    other_allegiance = sorted((youth | senior) - {cur})
    born = r["born_in"]
    p = {
        "name": r["player_name"],
        "pos": r["position"],
        "club": r["club_team"],
        "dob": r["date_of_birth"],
        "caps": int(r["caps"]) if r["caps"].isdigit() else 0,
        "born_in": born,
        "born_city": r["born_city"],
        "lat": float(r["born_lat"]) if r["born_lat"] else None,
        "lng": float(r["born_lng"]) if r["born_lng"] else None,
        "citizenships": [c.strip() for c in r["qualified_for_proxy_citizenship"].split(";") if c.strip()],
        "youth_for": sorted(youth),
        "senior_for": sorted(senior),
        "born_abroad": bool(born) and "born abroad" in r["notes"],
        "switched_from": other_allegiance,   # nations they played for but don't now
        "confidence": r["match_confidence"],
    }
    t["players"].append(p)

out_teams = []
for name, t in teams.items():
    players = t["players"]
    born_counts = Counter(p["born_in"] for p in players if p["born_in"])
    birth_countries = sorted(born_counts)
    n_abroad = sum(1 for p in players if p["born_abroad"])
    switchers = [p["name"] for p in players if p["switched_from"]]
    multi_cit = sum(1 for p in players if len(p["citizenships"]) > 1)
    # birth countries other than the home country, with counts (for clues + reveal)
    foreign_born_counts = {c: n for c, n in born_counts.items() if c != name}
    out_teams.append({
        "name": name,
        **TEAM_META.get(name, {}),
        "players": players,
        "birth_countries": birth_countries,            # Game B answer key (incl. home)
        "stats": {
            "squad_size": len(players),
            "n_born_abroad": n_abroad,
            "pct_born_abroad": round(100 * n_abroad / len(players)),
            "n_distinct_birth_countries": len(birth_countries),
            "n_switchers": len(switchers),
            "switchers": switchers,
            "n_multi_citizenship": multi_cit,
            "foreign_born_counts": foreign_born_counts,
            "top_foreign_origin": (max(foreign_born_counts, key=foreign_born_counts.get)
                                   if foreign_born_counts else None),
        },
    })

out_teams.sort(key=lambda t: t["name"])

# ---- attach ISO_A3 codes so the map can shade/match countries reliably ----
ALIASES = {  # our display name -> ISO_A3
    "USA": "USA", "Côte d'Ivoire": "CIV", "IR Iran": "IRN", "Congo DR": "COD",
    "Cabo Verde": "CPV", "Türkiye": "TUR", "South Korea": "KOR", "Czechia": "CZE",
    "Bosnia and Herzegovina": "BIH", "United Kingdom": "GBR", "Republic of Ireland": "IRL",
    "North Macedonia": "MKD", "DR Congo": "COD", "Cape Verde": "CPV",
    "England": "GBR", "Scotland": "GBR", "Wales": "GBR", "Northern Ireland": "GBR",
    "Isle of Man": "GBR", "Kingdom of Denmark": "DNK", "Vatican City": "VAT",
}
gj = json.load(open(os.path.join(HERE, "countries_50m.geojson")))
name_to_iso = {}
for f in gj["features"]:
    p = f["properties"]
    iso = p.get("ISO_A3_EH") or p.get("ISO_A3")
    if not iso or iso == "-99":
        iso = p.get("ISO_A3")
    for key in (p.get("NAME"), p.get("ADMIN"), p.get("NAME_LONG"), p.get("NAME_EN")):
        if key:
            name_to_iso[key] = iso

def iso_of(country):
    if country in ALIASES:
        return ALIASES[country]
    return name_to_iso.get(country)

unmapped = set()
for t in out_teams:
    t["iso3"] = iso_of(t["name"]) or ""
    if not t["iso3"]:
        unmapped.add(t["name"])
    t["birth_iso3"] = {}
    for c in t["birth_countries"]:
        code = iso_of(c)
        if code:
            t["birth_iso3"][c] = code
        else:
            unmapped.add(c)
if unmapped:
    print("WARNING unmapped country names (need an alias):", sorted(unmapped))

data = {
    "generated_from": "players_worldcup2026.csv",
    "n_teams": len(out_teams),
    "n_players": len(ROWS),
    "teams": out_teams,
}
with open(os.path.join(HERE, "app_data.json"), "w") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

# console summary
print(f"app_data.json: {len(out_teams)} teams, {len(ROWS)} players")
hard = sorted(out_teams, key=lambda t: -t["stats"]["n_distinct_birth_countries"])[:5]
print("most birth-country diversity (hardest Game B):",
      [(t["name"], t["stats"]["n_distinct_birth_countries"]) for t in hard])
allhome = [t["name"] for t in out_teams if t["stats"]["n_distinct_birth_countries"] == 1]
print("entirely home-born squads:", allhome or "none")
