#!/usr/bin/env python3
"""Transform players_worldcup2026.csv into app_data.json — the game-ready data layer.

born_in is derived from each player's birth COORDINATES via point-in-polygon against
countries_50m.geojson, so the country always matches where the pin lands. (The CSV's
born_in is unreliable for colonial-history places — e.g. Wikidata lists France as a
historical country for Algerian cities, so coordinate-based assignment is authoritative.)"""
import csv, json, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = list(csv.DictReader(open(os.path.join(HERE, "players_worldcup2026.csv"))))

NORMALIZE = {
    "United States of America": "USA", "United States": "USA",
    "Czech Republic": "Czechia", "Ivory Coast": "Côte d'Ivoire",
    "Republic of the Congo": "Congo", "Democratic Republic of the Congo": "Congo DR",
    "Iran": "IR Iran", "Turkey": "Türkiye", "Cape Verde": "Cabo Verde",
    "Republic of Korea": "South Korea", "Korea": "South Korea",
    "Bosnia and Herz.": "Bosnia and Herzegovina", "Kingdom of Denmark": "Denmark",
}
def norm(name):
    return NORMALIZE.get((name or "").strip(), (name or "").strip())

# ---- countries geojson: iso, display name, bbox, rings (for point-in-polygon) ----
GJ = json.load(open(os.path.join(HERE, "countries_50m.geojson")))
def feat_iso(p):
    i = p.get("ISO_A3_EH")
    if not i or i == "-99": i = p.get("ISO_A3")
    return i

COUNTRIES = []   # (iso, display_name, (minx,miny,maxx,maxy), polygons[list of [outer, *holes]])
for f in GJ["features"]:
    p = f["properties"]; g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    xs=[]; ys=[]
    for poly in polys:
        for x,y in poly[0]: xs.append(x); ys.append(y)
    COUNTRIES.append((feat_iso(p), norm(p.get("NAME")), (min(xs),min(ys),max(xs),max(ys)), polys))

def in_ring(x, y, ring):
    inside=False; n=len(ring); j=n-1
    for i in range(n):
        xi,yi=ring[i]; xj,yj=ring[j]
        if ((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/(yj-yi)+xi): inside=not inside
        j=i
    return inside

def country_at(lng, lat):
    for iso, name, (mnx,mny,mxx,mxy), polys in COUNTRIES:
        if lng<mnx or lng>mxx or lat<mny or lat>mxy: continue
        for poly in polys:
            if in_ring(lng, lat, poly[0]) and not any(in_ring(lng,lat,h) for h in poly[1:]):
                return iso, name
    return None, None

# team metadata
TEAM_META = {}
tcsv = os.path.join(HERE, "teams.csv")
if os.path.exists(tcsv):
    for t in csv.DictReader(open(tcsv)):
        TEAM_META[t["team_name"]] = {"fifa_code":t.get("fifa_code",""),
            "group":t.get("group_letter",""), "confederation":t.get("confederation","")}

# name -> iso (for team home countries) using the geojson + aliases
ALIASES = {"USA":"USA","Côte d'Ivoire":"CIV","IR Iran":"IRN","Congo DR":"COD",
    "Cabo Verde":"CPV","Türkiye":"TUR","South Korea":"KOR","Czechia":"CZE",
    "Bosnia and Herzegovina":"BIH","England":"GBR","Scotland":"GBR","Wales":"GBR",
    "Northern Ireland":"GBR","Curaçao":"CUW"}
NAME2ISO = {}
for iso,name,_,_ in COUNTRIES: NAME2ISO[name]=iso
def iso_of(country):
    return ALIASES.get(country) or NAME2ISO.get(country)

def parse_nats(field):
    out=set()
    for part in field.split(";"):
        part=part.strip()
        if part: out.add(part.split(" (")[0].strip())
    return out

teams = defaultdict(lambda: {"players": [], "name": None})
for r in ROWS:
    cur = r["currently_playing_for"]; t = teams[cur]; t["name"] = cur
    lat = float(r["born_lat"]) if r["born_lat"] else None
    lng = float(r["born_lng"]) if r["born_lng"] else None
    born_iso = born_name = None
    if lat is not None:
        born_iso, born_name = country_at(lng, lat)
    if not born_name:                       # fallback to CSV when PIP fails / no coords
        born_name = norm(r["born_in"]); born_iso = iso_of(born_name)
    youth=parse_nats(r["ever_youth_national_team"]); senior=parse_nats(r["ever_senior_national_team"])
    t["players"].append({
        "name": r["player_name"], "pos": r["position"], "club": r["club_team"],
        "dob": r["date_of_birth"], "caps": int(r["caps"]) if r["caps"].isdigit() else 0,
        "born_in": born_name, "born_iso": born_iso, "born_city": r["born_city"],
        "lat": lat, "lng": lng,
        # CSV marks needs_review="fallback" where the real birth city is unknown and
        # born_city/lat/lng were manually set to the player's country's CAPITAL as a
        # placeholder. born_in (country) is still trusted; born_city/lat/lng are NOT.
        # Game UI must not present born_city as a specific clue/fact when this is true.
        "born_city_is_fallback": r["needs_review"] == "fallback",
        "citizenships": [c.strip() for c in r["qualified_for_proxy_citizenship"].split(";") if c.strip()],
        "youth_for": sorted(youth), "senior_for": sorted(senior),
        "switched_from": sorted((youth|senior)-{cur}),
        "confidence": r["match_confidence"],
    })

out_teams=[]
for name,t in teams.items():
    players=t["players"]; tiso=iso_of(name)
    for p in players: p["born_abroad"] = bool(p["born_iso"]) and p["born_iso"]!=tiso
    born_counts=Counter(p["born_in"] for p in players if p["born_in"])
    birth_iso3={p["born_in"]:p["born_iso"] for p in players if p["born_in"] and p["born_iso"]}
    n_abroad=sum(1 for p in players if p["born_abroad"])
    switchers=[p["name"] for p in players if p["switched_from"]]
    # "foreign" = born countries other than HOME. Compare by ISO, not display name:
    # the home country's geojson NAME can differ from the team name (England/Scotland ->
    # "United Kingdom", Congo DR -> "Dem. Rep. Congo"), which would otherwise leak the
    # home-born players in as the top "foreign" origin.
    foreign={c:n for c,n in born_counts.items() if birth_iso3.get(c)!=tiso}
    out_teams.append({ "name":name, "iso3":tiso or "", **TEAM_META.get(name,{}),
        "players":players, "birth_countries":sorted(born_counts), "birth_iso3":birth_iso3,
        "stats":{ "squad_size":len(players), "n_born_abroad":n_abroad,
            "pct_born_abroad":round(100*n_abroad/len(players)),
            "n_distinct_birth_countries":len(born_counts), "n_switchers":len(switchers),
            "switchers":switchers,
            "n_multi_citizenship":sum(1 for p in players if len(p["citizenships"])>1),
            "foreign_born_counts":foreign,
            "top_foreign_origin":(max(foreign,key=foreign.get) if foreign else None) } })

out_teams.sort(key=lambda t:t["name"])
unmapped={t["name"] for t in out_teams if not t["iso3"]} | {c for t in out_teams for c in t["birth_countries"] if not iso_of(c)}
if unmapped: print("WARNING unmapped:", sorted(unmapped))
json.dump({"generated_from":"players_worldcup2026.csv","n_teams":len(out_teams),
    "n_players":len(ROWS),"teams":out_teams},
    open(os.path.join(HERE,"app_data.json"),"w"), ensure_ascii=False, separators=(",",":"))
print(f"app_data.json: {len(out_teams)} teams, {len(ROWS)} players")
alg=[t for t in out_teams if t["name"]=="Algeria"][0]
print("Algeria now:", alg["stats"]["n_born_abroad"],"/",alg["stats"]["squad_size"],
      "born abroad; counts:", dict(Counter(p["born_in"] for p in alg["players"])))
n_fallback=sum(1 for t in out_teams for p in t["players"] if p["born_city_is_fallback"])
print(f"players with born_city_is_fallback=True (capital-city placeholder, not a real birth city): {n_fallback}")
print("  -> these should not be shown as a specific born_city clue/fact in any game UI (see HANDOFF.md)")
