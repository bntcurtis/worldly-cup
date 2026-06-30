#!/usr/bin/env python3
"""Enrich the WC2026 roster with Wikidata-derived nationality data.

Outputs players_enriched.csv. Caches all HTTP results to disk so reruns resume.
"""
import csv, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
SEARCH_CACHE = os.path.join(CACHE_DIR, "search.json")
ENTITY_CACHE = os.path.join(CACHE_DIR, "entities.json")
UA = "WorldCup2026-PlayerOrigins/1.0 (research project; contact bntcurtis@gmail.com)"

def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)

search_cache = load(SEARCH_CACHE)
entity_cache = load(ENTITY_CACHE)

def http_get_json(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None

def wbsearch(name):
    if name in search_cache:
        return search_cache[name]
    params = urllib.parse.urlencode({
        "action": "wbsearchentities", "search": name, "language": "en",
        "uselang": "en", "format": "json", "type": "item", "limit": "12",
    })
    url = "https://www.wikidata.org/w/api.php?" + params
    data = http_get_json(url)
    ids = [s["id"] for s in data.get("search", [])]
    search_cache[name] = ids
    return ids

def get_entities(ids):
    """Batch fetch entities (claims+labels), cache each individually."""
    missing = [i for i in ids if i not in entity_cache]
    for batch_start in range(0, len(missing), 45):
        batch = missing[batch_start:batch_start + 45]
        params = urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "claims|labels", "languages": "en", "format": "json",
        })
        url = "https://www.wikidata.org/w/api.php?" + params
        data = http_get_json(url)
        for qid, ent in data.get("entities", {}).items():
            entity_cache[qid] = compact(ent)
        time.sleep(0.05)
    return {i: entity_cache.get(i) for i in ids}

WIKI_CACHE = os.path.join(CACHE_DIR, "wiki_squad.json")
def harvest_wikipedia_squads():
    """Harvest every player linked from the English Wikipedia '2026 FIFA World Cup
    squads' page, resolve enwiki titles -> Wikidata QIDs, and index footballers by
    exact date of birth. This recovers players the name-search missed (Arabic/Korean
    romanization, mangled source names) because it never relies on the roster spelling.
    Returns dob (YYYY-MM-DD) -> [qid, ...] for footballers."""
    cache = load(WIKI_CACHE)
    if not cache.get("titles"):
        params = urllib.parse.urlencode({"action": "parse",
            "page": "2026 FIFA World Cup squads", "prop": "links", "format": "json"})
        d = http_get_json("https://en.wikipedia.org/w/api.php?" + params)
        cache["titles"] = [l["*"] for l in d["parse"]["links"]
                           if l.get("ns") == 0 and l.get("exists") == ""]
        save(WIKI_CACHE, cache)
    titles = cache["titles"]
    wiki_qids = set(cache.get("wiki_qids", []))
    # resolve enwiki titles -> Wikidata entities (land in entity_cache, track the QIDs)
    if not wiki_qids:
        for s in range(0, len(titles), 45):
            batch = titles[s:s + 45]
            params = urllib.parse.urlencode({"action": "wbgetentities", "sites": "enwiki",
                "titles": "|".join(batch), "props": "claims|labels", "languages": "en",
                "redirects": "yes", "format": "json"})
            data = http_get_json("https://www.wikidata.org/w/api.php?" + params)
            for qid, ent in data.get("entities", {}).items():
                if qid.startswith("Q"):
                    entity_cache[qid] = compact(ent)
                    wiki_qids.add(qid)
            time.sleep(0.05)
        cache["wiki_qids"] = sorted(wiki_qids)
        save(WIKI_CACHE, cache)
        save(ENTITY_CACHE, entity_cache)
    else:
        # entity cache may have been rebuilt since; ensure these QIDs are present
        get_entities(sorted(wiki_qids))
    # index the squad-page footballers by exact DOB
    dob_index = {}
    for qid in wiki_qids:
        e = entity_cache.get(qid)
        if not e or not (set(ids_of(e, "P106")) & FOOTBALLER):
            continue
        d = dob_of(e)
        if d:
            dob_index.setdefault(d, []).append(qid)
    return dob_index

def compact(ent):
    """Keep only the props we care about to shrink the cache."""
    out = {"label": None, "claims": {}}
    out["label"] = (ent.get("labels", {}).get("en", {}) or {}).get("value")
    keep = ["P569", "P106", "P19", "P27", "P54", "P1532", "P31", "P17", "P580", "P582", "P625"]
    claims = ent.get("claims", {})
    for p in keep:
        vals = []
        for c in claims.get(p, []):
            ms = c.get("mainsnak", {})
            dv = ms.get("datavalue", {})
            v = dv.get("value")
            if isinstance(v, dict) and "id" in v:        # entity ref
                qual = {}
                for qp in ("P580", "P582"):              # start/end time on team membership
                    q = c.get("qualifiers", {}).get(qp)
                    if q:
                        qv = q[0].get("datavalue", {}).get("value", {})
                        qual[qp] = qv.get("time")
                vals.append({"id": v["id"], "qual": qual})
            elif isinstance(v, dict) and "time" in v:    # time value
                vals.append({"time": v["time"]})
            elif v is not None:
                vals.append({"raw": v})
        if vals:
            out["claims"][p] = vals
    return out

def ids_of(ent, p):
    return [v["id"] for v in ent.get("claims", {}).get(p, []) if "id" in v]

def is_modern_country(qid):
    """A present-day country: instance of 'country' (Q6256) and NOT instance of
    'historical country' (Q3024240). Reliably separates Uzbekistan from
    'Tashkent Khanate', Sweden from 'Union between Sweden and Norway', etc."""
    e = entity_cache.get(qid)
    if not e:
        return False
    p31 = set(ids_of(e, "P31"))
    return "Q6256" in p31 and "Q3024240" not in p31

def dob_of(ent):
    for v in ent.get("claims", {}).get("P569", []):
        t = v.get("time")
        if t:  # like +2000-02-25T00:00:00Z
            return t[1:11]  # YYYY-MM-DD
    return None

# A national team is detected purely from its English label: it contains the word
# "national" and "football team". This reliably includes senior + every youth level
# (U-15..U-23, Olympic) and excludes clubs. (QID-based P31 matching proved unreliable
# because some club subclasses share QIDs with youth-team classes.)
def is_national_team(label):
    low = (label or "").lower()
    return "national" in low and ("football team" in low or "soccer team" in low)

def team_level(label):
    """Return 'senior' or a youth level string parsed from the team label."""
    low = (label or "").lower()
    m = re.search(r"under-(\d+)", low)
    if m:
        return "U-" + m.group(1)
    if "olympic" in low:
        return "Olympic"
    if re.search(r"\bunder\b", low):
        return "youth"
    return "senior"

# strip the boilerplate suffix to recover a clean country name from a team label.
# Parsing the label is more reliable than P17 because the four UK home nations all
# carry P17 = United Kingdom, which would erase "England"/"Scotland"/etc.
_TEAM_SUFFIX = re.compile(
    r"\s+(men's|women's|boys'|girls')?\s*(b\s+)?national\s+(under-\d+\s+)?"
    r"(association\s+|amateur\s+)?(football|soccer)\s+team$", re.I)
def country_from_team_label(label):
    out = _TEAM_SUFFIX.sub("", label or "").strip()
    return out if out and out != label else ""   # "" means parse failed

# Canonicalize country labels so roster names and Wikidata labels agree.
NORMALIZE = {
    "Czech Republic": "Czechia",
    "United States": "USA", "United States of America": "USA",
    "Ivory Coast": "Côte d'Ivoire",
    "Iran": "IR Iran", "Islamic Republic of Iran": "IR Iran",
    "Turkey": "Türkiye",
    "Cape Verde": "Cabo Verde",
    "Democratic Republic of the Congo": "Congo DR", "DR Congo": "Congo DR",
    "Republic of Korea": "South Korea", "Korea": "South Korea",
    "Kingdom of the Netherlands": "Netherlands",
}
def norm(name):
    return NORMALIZE.get((name or "").strip(), (name or "").strip())

# Home nations of the UK: a player born in "United Kingdom" who plays for one of
# these is not "born abroad" (P17=UK can't distinguish the four nations).
UK_NATIONS = {"England", "Scotland", "Wales", "Northern Ireland"}
def same_country(born, current):
    if not born or not current:
        return True
    if born == current:
        return True
    if born == "United Kingdom" and current in UK_NATIONS:
        return True
    return False

FOOTBALLER = {"Q937857", "Q628099"}  # association football player, footballer

def name_variants(name):
    """Roster names are often full birth names; Wikidata uses common names.
    Generate fallbacks, most-specific first, deduped."""
    t = name.split()
    out = [name]
    if len(t) >= 3:
        out.append(t[0] + " " + t[-2] + " " + t[-1])  # first + last two
        out.append(t[0] + " " + t[-1])                # first + last
        out.append(t[-2] + " " + t[-1])               # last two
    if len(t) >= 2:
        out.append(t[-1] + " " + t[0])                # reversed (e.g. Korean "Hwang Inbeom")
    seen, r = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v); r.append(v)
    return r

def main():
    rows = []
    with open(os.path.join(HERE, "squads.csv")) as f:
        rows = list(csv.DictReader(f))
    teams = {}
    with open(os.path.join(HERE, "teams.csv")) as f:
        for t in csv.DictReader(f):
            teams[t["team_id"]] = t["team_name"]

    # ---- pass 1+2: match each player to a Wikidata entity, disambiguating by
    # exact DOB. Try name variants only until a high-confidence DOB match is found. ----
    n = len(rows)
    for i, r in enumerate(rows):
        target_dob = r["date_of_birth"]
        best, best_conf, first_fb = None, "unmatched", None
        for variant in name_variants(r["player_name"]):
            cands = wbsearch(variant)
            get_entities(cands)               # ensure candidates are cached
            for qid in cands:
                ent = entity_cache.get(qid)
                if not ent:
                    continue
                is_fb = bool(set(ids_of(ent, "P106")) & FOOTBALLER)
                if is_fb and first_fb is None:
                    first_fb = qid
                if target_dob and dob_of(ent) == target_dob:
                    best, best_conf = qid, ("high" if is_fb else "medium")
                    break
            if best:
                break                          # stop trying variants once matched
        if best is None and first_fb is not None:
            best, best_conf = first_fb, "low"  # name-only guess, DOB unverified
        r["_qid"], r["_conf"] = best, best_conf
        r["_source"] = "wikidata-name+dob" if best else ""
        if i % 50 == 0:
            save(SEARCH_CACHE, search_cache); save(ENTITY_CACHE, entity_cache)
            print(f"  match {i}/{n}", file=sys.stderr)
    save(SEARCH_CACHE, search_cache); save(ENTITY_CACHE, entity_cache)

    # ---- pass 2.5: rescue unmatched/low via the Wikipedia squad page, joined on
    # exact DOB (+ nationality when DOBs collide). Spelling-independent. ----
    print("harvesting Wikipedia squad pages...", file=sys.stderr)
    dob_index = harvest_wikipedia_squads()

    def nat_set(qid):
        """Normalized citizenship + country-for-sport labels for a candidate."""
        e = entity_cache.get(qid)
        if not e:
            return set()
        qs = ids_of(e, "P27") + ids_of(e, "P1532")
        get_entities(qs)
        return {norm((entity_cache.get(q) or {}).get("label") or "") for q in qs}

    rescued = 0
    for r in rows:
        if r["_conf"] == "high":
            continue
        cands = dob_index.get(r["date_of_birth"], [])
        if not cands:
            continue
        team = norm(teams.get(r["team_id"], ""))
        pick = None
        if len(cands) == 1:
            pick = cands[0]
        else:  # DOB collision: disambiguate by nationality matching the squad
            good = [q for q in cands if team in nat_set(q)]
            if len(good) == 1:
                pick = good[0]
        if pick:
            r["_qid"], r["_conf"], r["_source"] = pick, "high", "wikipedia-squad"
            rescued += 1
    save(ENTITY_CACHE, entity_cache)
    print(f"rescued via Wikipedia: {rescued}", file=sys.stderr)

    # ---- pass 3: collect referenced QIDs (places, citizenships, teams) ----
    refs = set()
    for r in rows:
        ent = entity_cache.get(r["_qid"]) if r["_qid"] else None
        if not ent:
            continue
        refs.update(ids_of(ent, "P19"))
        refs.update(ids_of(ent, "P27"))
        refs.update(ids_of(ent, "P54"))
        refs.update(ids_of(ent, "P1532"))
    get_entities(sorted(refs))
    save(ENTITY_CACHE, entity_cache)
    # both birthplaces and national teams carry a P17 country we need labels for
    countries = set()
    for q in refs:
        e = entity_cache.get(q)
        if e:
            countries.update(ids_of(e, "P17"))
    get_entities(sorted(countries))
    save(ENTITY_CACHE, entity_cache)

    def label(qid):
        e = entity_cache.get(qid)
        return e["label"] if e and e.get("label") else qid

    # ---- pass 4: derive output columns ----
    out_rows = []
    for r in rows:
        current = norm(teams.get(r["team_id"], ""))
        ent = entity_cache.get(r["_qid"]) if r["_qid"] else None
        born_country = ""
        born_city = ""
        born_lat = born_lng = ""
        born_is_historical_only = False
        citizenships = []
        ever_current, ever_youth = [], []
        if ent:
            # birthplace: city label, coordinates (P625), and present-day country (P17)
            for pid in ids_of(ent, "P19"):
                pe = entity_cache.get(pid)
                if not pe:
                    continue
                born_city = pe.get("label") or ""
                for c in pe.get("claims", {}).get("P625", []):
                    coord = c.get("raw")
                    if isinstance(coord, dict) and "latitude" in coord:
                        born_lat = round(coord["latitude"], 5)
                        born_lng = round(coord["longitude"], 5)
                        break
                cqids = ids_of(pe, "P17")
                modern = [q for q in cqids if is_modern_country(q)]
                if modern:
                    born_country = norm(label(modern[-1]))
                elif cqids:
                    born_country = norm(label(cqids[-1])); born_is_historical_only = True
                break
            citizenships = [norm(label(q)) for q in ids_of(ent, "P27")]
            # national teams ever played for (senior vs youth)
            for v in ent.get("claims", {}).get("P54", []):
                tid = v.get("id")
                te = entity_cache.get(tid) if tid else None
                if not te:
                    continue
                lbl = te.get("label") or ""
                if not is_national_team(lbl):
                    continue
                parsed = country_from_team_label(lbl)   # reliable; "" if it failed
                tc = ids_of(te, "P17")
                cname = norm(parsed if parsed else (label(tc[0]) if tc else lbl))
                level = team_level(lbl)
                if level == "senior":
                    ever_current.append(cname)
                else:
                    ever_youth.append(f"{cname} ({level})")

        # ---- confidence / review flags ----
        notes = []
        conf = r["_conf"]
        if conf == "unmatched":
            notes.append("no Wikidata match found")
        elif conf == "low":
            notes.append("matched by name only, DOB did not match - VERIFY")
        if ent and not born_country:
            notes.append("birthplace missing on Wikidata")
        if born_is_historical_only:
            notes.append("birthplace resolved to a historical state - VERIFY")
        if ent and not citizenships:
            notes.append("citizenship missing on Wikidata")
        # interesting cases worth a human glance
        if born_country and not same_country(born_country, current):
            notes.append("born abroad")
        senior_set = set(ever_current)
        if senior_set and current not in senior_set:
            notes.append("senior caps listed only for other nation(s) - possible switch/mismatch")
        if len([c for c in senior_set if c != current]) >= 1 and current in senior_set:
            notes.append("senior caps for multiple nations")

        out_rows.append({
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "date_of_birth": r["date_of_birth"],
            "position": r["position"],
            "club_team": r["club_team"],
            "caps": r["caps"],
            "currently_playing_for": current,
            "born_in": born_country,
            "born_city": born_city,
            "born_lat": born_lat,
            "born_lng": born_lng,
            "qualified_for_proxy_citizenship": "; ".join(citizenships),
            "ever_senior_national_team": "; ".join(sorted(set(ever_current))),
            "ever_youth_national_team": "; ".join(sorted(set(ever_youth))),
            "wikidata_qid": r["_qid"] or "",
            "match_confidence": conf,
            "match_source": r.get("_source", ""),
            "needs_review": "YES" if (conf in ("unmatched", "low") or
                                      born_is_historical_only or
                                      (ent and not born_country)) else "",
            "notes": "; ".join(notes),
        })

    out_path = os.path.join(HERE, "players_enriched.csv")
    cols = list(out_rows[0].keys())
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    # quick summary to stderr
    from collections import Counter
    cc = Counter(r["match_confidence"] for r in out_rows)
    abroad = sum(1 for r in out_rows if "born abroad" in r["notes"])
    print(f"DONE -> {out_path}", file=sys.stderr)
    print("confidence:", dict(cc), file=sys.stderr)
    print("born abroad:", abroad, file=sys.stderr)

if __name__ == "__main__":
    main()
