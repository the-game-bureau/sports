#!/usr/bin/env python3
# maker.py — build a unified teams.xml containing NCAA (SEC, American Conference, Big Sky) + NFL teams.
#
# NCAA sources (scraped at runtime):
#   FBS programs table: https://en.wikipedia.org/wiki/List_of_NCAA_Division_I_FBS_football_programs
#   FCS programs table: https://en.wikipedia.org/wiki/List_of_NCAA_Division_I_FCS_football_programs
#   2025 American Conference season (authoritative AC membership):
#       https://en.wikipedia.org/wiki/2025_American_Conference_football_season
#   2025 SEC season (SEC membership):
#       https://en.wikipedia.org/wiki/2025_Southeastern_Conference_football_season
#
# NFL source:
#   Teams index: https://www.nfl.com/teams
#
# Output:
#   ./teams.xml (pretty-printed)

import sys
import time
import re
from typing import List, Dict, Optional, Tuple, Set
import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree

# -------------------- Config --------------------

FBS_URL = "https://en.wikipedia.org/wiki/List_of_NCAA_Division_I_FBS_football_programs"
FCS_URL = "https://en.wikipedia.org/wiki/List_of_NCAA_Division_I_FCS_football_programs"
AC_SEASON_URL = "https://en.wikipedia.org/wiki/2025_American_Conference_football_season"
SEC_SEASON_URL = "https://en.wikipedia.org/wiki/2025_Southeastern_Conference_football_season"
NFL_TEAMS_URL = "https://www.nfl.com/teams"

USER_AGENT = "Mozilla/5.0 (compatible; maker-teamsxml/4.0)"
TIMEOUT = 30

# -------------------- HTTP --------------------

def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

# -------------------- Small utils --------------------

def norm(s: str) -> str:
    """normalize for matching (letters+digits only, lowercase)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def normalize_header(h: str) -> str:
    """Map various table header labels into canonical keys."""
    h = (h or "")
    h = re.sub(r"\[[^\]]*\]", "", h)  # strip footnotes like [1], [a]
    h = h.replace("\xa0", " ").strip().lower()
    h = re.sub(r"\s+", " ", h)
    if "conference" in h: return "conference"
    if "stadium" in h: return "stadium"
    if "school" in h or "university" in h or "institution" in h: return "school"
    if h in ("team", "nickname", "mascot"): return "team"
    if "first" in h and "season" in h: return "first_season"
    if "joined" in h: return "joined"
    if h == "location": return "location"
    if h == "city": return "city"
    if h == "state": return "state"
    if "link" in h: return "link"
    if "subdivision" in h or h in ("ncaa division", "division"): return "subdivision"
    return h

def split_location(rec: Dict[str, str]) -> Tuple[str, str]:
    """Return (city, state) with reasonable fallbacks from a row record."""
    city = (rec.get("city") or "").strip()
    state = (rec.get("state") or "").strip()
    if not city and not state:
        loc = (rec.get("location") or "").strip()
        if "," in loc:
            left, right = [p.strip() for p in loc.split(",", 1)]
            city = left
            state = re.sub(r"\s*\(.*\)$", "", right).strip()
        else:
            city = loc
    return city, state

def short_conf(full: str) -> str:
    s = (full or "").lower()
    if "southeastern" in s: return "SEC"
    if "big sky" in s: return "Big Sky"
    if "american" in s: return "AC"
    return full or ""

# -------------------- Wikipedia: generic table parsing --------------------

def find_wikitable_with_conference(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    for tbl in soup.select("table.wikitable"):
        ths = [normalize_header(th.get_text(strip=True)) for th in tbl.select("tr th")]
        if any(h == "conference" for h in ths):
            return tbl
    return None

def parse_program_table(tbl: BeautifulSoup) -> List[Dict[str, str]]:
    """Parse a wikitable of programs into dict rows with flexible headers."""
    rows = []
    trs = tbl.select("tr")
    if not trs:
        return rows
    header_cells = trs[0].find_all(["th", "td"])
    headers = [normalize_header(c.get_text(strip=True)) for c in header_cells]
    idx = {h: i for i, h in enumerate(headers)}

    for tr in trs[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        if sum(1 for c in cells if c.get_text(strip=True)) < 2:
            continue

        def cell_text(col: str) -> str:
            i = idx.get(col)
            if i is None or i >= len(cells): return ""
            link = cells[i].find("a")
            if link and link.get_text(strip=True): return link.get_text(strip=True)
            return cells[i].get_text(" ", strip=True)

        def cell_link(col: str) -> str:
            i = idx.get(col)
            if i is None or i >= len(cells): return ""
            link = cells[i].find("a", href=True)
            if not link: return ""
            href = link["href"]
            if href.startswith("//"): return "https:" + href
            if href.startswith("/"):  return "https://en.wikipedia.org" + href
            return href

        record = {
            "school": cell_text("school"),
            "team": cell_text("team"),
            "conference": cell_text("conference"),
            "location": cell_text("location"),
            "city": cell_text("city"),
            "state": cell_text("state"),
            "stadium": cell_text("stadium"),
            "first_season": cell_text("first_season"),
            "joined": cell_text("joined"),
            "link": cell_link("school") or cell_link("team") or cell_link("link"),
        }
        # Clean values
        for k, v in list(record.items()):
            v = re.sub(r"\[[^\]]+\]", "", v)
            v = v.replace("\xa0", " ").strip()
            record[k] = v

        rows.append(record)
    return rows

# -------------------- Membership scrapers (AC / SEC) --------------------

def scrape_members_from_season(url: str) -> List[str]:
    """
    Scrape a season page's standings table(s) and return visible team names (first column).
    Flexible enough to handle divisions/no divisions.
    """
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    names: List[str] = []
    for tbl in soup.select("table.wikitable"):
        headers = [th.get_text(" ", strip=True).lower() for th in tbl.select("tr th")]
        if not headers:
            continue
        if "team" in " | ".join(headers):
            for tr in tbl.select("tr")[1:]:
                tds = tr.find_all("td")
                if not tds:
                    continue
                a = tds[0].find("a")
                nm = (a.get_text(strip=True) if a else tds[0].get_text(" ", strip=True)).strip()
                if nm:
                    names.append(nm)
    # de-dupe while preserving order
    seen, out = set(), []
    for n in names:
        k = norm(n)
        if k in seen:
            continue
        seen.add(k); out.append(n)
    return out

def get_ac_member_keys() -> Set[str]:
    raw = scrape_members_from_season(AC_SEASON_URL)
    # Exact matching with a few common short->long aliases
    aliases = {
        "uab": "university of alabama at birmingham",
        "utsa": "university of texas at san antonio",
        "usf": "south florida",
        "fau": "florida atlantic",
        "ecu": "east carolina",
    }
    expanded = []
    for n in raw:
        expanded.append(n)
        k = norm(n)
        for short, full in aliases.items():
            if k == norm(short):
                expanded.append(full)
    keys = {norm(n) for n in expanded}
    print(f"[AC] Season page teams: {len(keys)} -> {sorted(list(keys))}", file=sys.stderr)
    return keys

def get_sec_member_keys_from_season() -> Optional[Set[str]]:
    try:
        raw = scrape_members_from_season(SEC_SEASON_URL)
        if not raw:
            return None
        keys = {norm(n) for n in raw}
        print(f"[SEC] Season page teams: {len(keys)} -> {sorted(list(keys))}", file=sys.stderr)
        return keys
    except Exception as e:
        print(f"[SEC] Season page fallback triggered: {e}", file=sys.stderr)
        return None

def classify_conference_from_cell(raw_conf: str) -> Optional[str]:
    """Fallback classification from program table cells for SEC/Big Sky only."""
    if not raw_conf:
        return None
    raw = raw_conf.strip()
    key = re.sub(r"[^a-z]", "", raw.lower())

    # Exclude Atlantic Coast (ACC) explicitly
    if "atlanticcoast" in key or re.search(r"\bacc\b", raw.lower()):
        return None

    if "southeasternconference" in key or re.search(r"\bsec\b", raw.lower()):
        return "Southeastern Conference"
    if "bigskyconference" in key or "bigsky" in key:
        return "Big Sky Conference"
    return None

# -------------------- NCAA record building --------------------

def build_ncaa_records() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []

    # FBS programs table (for SEC + to enrich AC)
    fbs_soup = BeautifulSoup(fetch(FBS_URL), "html.parser")
    fbs_tbl = find_wikitable_with_conference(fbs_soup)
    if not fbs_tbl:
        raise RuntimeError("Could not find FBS wikitable with a Conference column.")
    fbs_rows = parse_program_table(fbs_tbl)

    # AC membership (exact match)
    ac_keys = get_ac_member_keys()
    kept_ac = 0

    # SEC membership (prefer season page; fallback to FBS table parse)
    sec_keys = get_sec_member_keys_from_season()
    if not sec_keys:
        sec_keys = set()
        for r in fbs_rows:
            conf = classify_conference_from_cell(r.get("conference", ""))
            if conf == "Southeastern Conference":
                sec_keys.add(norm(r.get("school", "")))
        print(f"[SEC] Fallback derived keys: {len(sec_keys)} -> {sorted(list(sec_keys))}", file=sys.stderr)
    kept_sec = 0

    # Iterate FBS once; pick AC/SEC based on membership sets
    for r in fbs_rows:
        school = r.get("school", "")
        team = r.get("team", "")
        city, state = split_location(r)
        url = r.get("link", "")
        school_k, team_k = norm(school), norm(team)

        # SEC
        if school_k in sec_keys or team_k in sec_keys:
            out.append({
                "league": "NCAA",
                "name": f"{school} {team}".strip(),
                "school": school,
                "team": team,
                "city": city, "state": state,
                "conference": "Southeastern Conference",
                "conference_short": short_conf("Southeastern Conference"),
                "subdivision": "FBS",
                "stadium": r.get("stadium", ""),
                "first_season": r.get("first_season", ""),
                "joined": r.get("joined", ""),
                "url": url,
            })
            kept_sec += 1
            continue

        # AC
        if school_k in ac_keys or team_k in ac_keys:
            out.append({
                "league": "NCAA",
                "name": f"{school} {team}".strip(),
                "school": school,
                "team": team,
                "city": city, "state": state,
                "conference": "American Conference",
                "conference_short": short_conf("American Conference"),
                "subdivision": "FBS",
                "stadium": r.get("stadium", ""),
                "first_season": r.get("first_season", ""),
                "joined": r.get("joined", ""),
                "url": url,
            })
            kept_ac += 1

    print(f"[FBS] Kept {kept_sec} SEC and {kept_ac} AC teams.", file=sys.stderr)

    # FCS programs table (for Big Sky)
    fcs_soup = BeautifulSoup(fetch(FCS_URL), "html.parser")
    fcs_tbl = find_wikitable_with_conference(fcs_soup)
    if not fcs_tbl:
        raise RuntimeError("Could not find FCS wikitable with a Conference column.")
    fcs_rows = parse_program_table(fcs_tbl)

    kept_bigsky = 0
    for r in fcs_rows:
        conf_name = classify_conference_from_cell(r.get("conference", ""))
        if conf_name != "Big Sky Conference":
            continue
        city, state = split_location(r)
        out.append({
            "league": "NCAA",
            "name": f"{(r.get('school') or '').strip()} {(r.get('team') or '').strip()}".strip(),
            "school": r.get("school", ""),
            "team": r.get("team", ""),
            "city": city, "state": state,
            "conference": "Big Sky Conference",
            "conference_short": short_conf("Big Sky Conference"),
            "subdivision": "FCS",
            "stadium": r.get("stadium", ""),
            "first_season": r.get("first_season", ""),
            "joined": r.get("joined", ""),
            "url": r.get("link", ""),
        })
        kept_bigsky += 1

    print(f"[FCS] Kept {kept_bigsky} Big Sky teams.", file=sys.stderr)
    return out

# -------------------- NFL scraper --------------------

def extract_first_src_from_srcset(srcset: str) -> Optional[str]:
    if not srcset:
        return None
    # srcset like: "https://... 1x, https://... 2x" or just a URL
    parts = [p.strip() for p in srcset.split(",")]
    if not parts:
        return None
    first = parts[0].split(" ")[0].strip()
    return first or None

def build_nfl_records() -> List[Dict[str, str]]:
    html = fetch(NFL_TEAMS_URL)
    soup = BeautifulSoup(html, "html.parser")

    teams = []
    promos = soup.select("div.nfl-c-custom-promo")
    if not promos:
        # fallback: newer layout sometimes nests in section
        promos = soup.select("section a[href*='/teams/']")

    for promo in promos:
        try:
            # Name
            name_tag = promo.select_one("h4 p") or promo.select_one("h4") or promo.select_one("p")
            name = name_tag.get_text(strip=True) if name_tag else None

            # Link
            link_tag = promo.select_one("a[href*='/teams/']")
            url = None
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                url = "https://www.nfl.com" + href if href.startswith("/") else href

            # Logo (try <picture><source data-srcset> first; fallback to <img src>)
            logo = None
            src_tag = promo.select_one("picture source")
            if src_tag:
                logo = extract_first_src_from_srcset(src_tag.get("data-srcset") or src_tag.get("srcset") or "")
            if not logo:
                img_tag = promo.select_one("img")
                if img_tag:
                    logo = img_tag.get("data-src") or img_tag.get("src")

            # Background image from style attribute
            background = None
            style = promo.get("style", "")
            m = re.search(r"background-image:\s*url\(([^)]+)\)", style)
            if m:
                background = m.group(1)

            # Only keep well-formed entries with a name and a teams link
            if not (name and url and "/teams/" in url):
                continue

            teams.append({
                "league": "NFL",
                "name": name,
                "url": url,
                "logo": logo or "",
                "background": background or "",
            })
        except Exception:
            continue

    # Deduplicate by URL
    seen, uniq = set(), []
    for t in teams:
        k = t["url"]
        if k in seen:
            continue
        seen.add(k); uniq.append(t)

    print(f"[NFL] Parsed {len(uniq)} teams.", file=sys.stderr)
    return uniq

# -------------------- XML writer --------------------

def write_xml(records_ncaa: List[Dict[str, str]], records_nfl: List[Dict[str, str]], out_path: str = "teams.xml") -> None:
    root = Element("teams")

    meta = SubElement(root, "meta")
    SubElement(meta, "generated_by").text = "maker.py"
    SubElement(meta, "source_fbs").text = FBS_URL
    SubElement(meta, "source_fcs").text = FCS_URL
    SubElement(meta, "source_ac").text = AC_SEASON_URL
    SubElement(meta, "source_sec").text = SEC_SEASON_URL
    SubElement(meta, "source_nfl").text = NFL_TEAMS_URL
    SubElement(meta, "generated_at").text = time.strftime("%Y-%m-%dT%H:%M:%S")

    def add(parent, tag, text):
        el = SubElement(parent, tag); el.text = text or ""; return el

    # NCAA teams
    for r in records_ncaa:
        team = SubElement(root, "team")
        add(team, "league", r.get("league"))
        add(team, "name", r.get("name"))
        add(team, "school", r.get("school"))
        add(team, "nickname", r.get("team"))
        add(team, "city", r.get("city"))
        add(team, "state", r.get("state"))
        add(team, "conference", r.get("conference"))
        add(team, "conference_short", r.get("conference_short"))
        add(team, "subdivision", r.get("subdivision"))
        add(team, "stadium", r.get("stadium"))
        add(team, "first_season", r.get("first_season"))
        add(team, "joined_conference", r.get("joined"))
        add(team, "url", r.get("url"))

    # NFL teams
    for r in records_nfl:
        team = SubElement(root, "team")
        add(team, "league", r.get("league"))
        add(team, "name", r.get("name"))
        add(team, "url", r.get("url"))
        add(team, "logo", r.get("logo"))
        add(team, "background", r.get("background"))

    # Pretty print (Python 3.9+)
    try:
        import xml.etree.ElementTree as ET
        ET.indent(root, space="  ")
    except Exception:
        pass

    ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {out_path} with {len(records_ncaa) + len(records_nfl)} total teams.", file=sys.stderr)

# -------------------- main --------------------

def main():
    try:
        ncaa = build_ncaa_records()
        nfl = build_nfl_records()
        write_xml(ncaa, nfl, "teams.xml")
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr); sys.exit(1)
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
