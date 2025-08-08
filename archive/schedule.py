import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
import time

# ---------- Shared helpers ----------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_json(url, timeout=30):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def looks_like_conference(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    keys = [
        "conference", "sec", "acc", "big ", "pac", "sun belt", "mountain west",
        "american", "mac", "conference usa", "ivy", "patriot", "colonial",
        "big sky", "valley", "southland", "ohio valley", "southern", "big south",
        "northeast", "pioneer", "meac", "swac", "united athletic", "independent",
        "fbs", "fcs", "aac"
    ]
    return any(k in n for k in keys)

def normalize_conf(name: str) -> str:
    if not name:
        return "Independent"
    n = name.strip().lower()

    # Map common variants; retain original if unknown (avoid over-labeling as Independent)
    mapping = [
        (["southeastern","sec"], "SEC"),
        (["big ten","big 10","b1g"], "Big Ten"),
        (["atlantic coast","acc"], "ACC"),
        (["big 12","big twelve"], "Big 12"),
        (["pac-12","pac 12","pacific-12","pacific 12"], "Pac-12"),
        (["american athletic","aac","the american","american conference"], "American Athletic Conference"),
        (["mountain west","mwc"], "Mountain West"),
        (["conference usa","c-usa","cusa"], "Conference USA"),
        (["mid-american","mac"], "MAC"),
        (["sun belt"], "Sun Belt"),
        (["ivy"], "Ivy League"),
        (["patriot"], "Patriot League"),
        (["colonial athletic","caa"], "Colonial Athletic Association"),
        (["big sky"], "Big Sky"),
        (["missouri valley","mvfc"], "Missouri Valley Football Conference"),
        (["southland"], "Southland Conference"),
        (["ohio valley","ovc"], "Ohio Valley Conference"),
        (["southern conference","socon"], "Southern Conference"),
        (["big south"], "Big South Conference"),
        (["northeast","nec"], "Northeast Conference"),
        (["pioneer football","pioneer"], "Pioneer Football League"),
        (["meac"], "MEAC"),
        (["swac"], "SWAC"),
        (["united athletic","uac"], "United Athletic Conference"),
        (["independent","independents","fbs independents","fcs independents"], "Independent"),
    ]
    for keys, label in mapping:
        if any(k in n for k in keys):
            return label
    # If ESPN already gives a sane name like "ASUN–WAC" etc, keep it
    return name.strip()

def iso_to_local_string(iso):
    if not iso:
        return "TBD"
    try:
        # ESPN gives UTC Z strings; make readable local-ish string without tz math
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return iso

# ---------- College Football (CFB) ----------

def cfb_build_conference_index(year: int) -> dict:
    """
    Walk ESPN standings tree. For each team id, store the nearest ancestor that
    looks like a conference (not a division/region header unless that's the only label).
    """
    url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/standings?season={year}"
    data = get_json(url)
    idx = {}

    def walk(node, nearest_conf=None):
        name = node.get("name") or node.get("displayName") or node.get("shortName") or ""
        new_nearest = nearest_conf
        if looks_like_conference(name):
            new_nearest = name  # update when we find a conf-like node

        # Map teams in this node to the nearest conference ancestor
        standings = node.get("standings", {})
        for entry in standings.get("entries", []):
            team = entry.get("team", {})
            tid = str(team.get("id") or "")
            if tid and new_nearest:
                idx[tid] = normalize_conf(new_nearest)

        for child in node.get("children", []):
            walk(child, new_nearest)

    # Root and children
    if data:
        walk(data, None)
        for child in data.get("children", []):
            walk(child, None)

    return idx

def cfb_backfill_team_conf(team_id: str) -> str:
    """
    If standings miss a team, hit team details once to try to infer a conference.
    """
    if not team_id:
        return "Independent"
    url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{team_id}"
    data = get_json(url)
    team = data.get("team") or {}
    # Look at 'groups' first
    groups = team.get("groups") or []
    for g in groups:
        gname = (g.get("name") or "").strip()
        if looks_like_conference(gname):
            return normalize_conf(gname)
        parent = g.get("parent") or {}
        pname = (parent.get("name") or "").strip()
        if looks_like_conference(pname):
            return normalize_conf(pname)
    # Fallback direct
    conf = team.get("conference")
    if isinstance(conf, dict):
        return normalize_conf(conf.get("name") or conf.get("displayName") or "")
    if isinstance(conf, str):
        return normalize_conf(conf)

    return "Independent"

def build_cfb_section(root, year=2025, max_weeks=15):
    conf_index = cfb_build_conference_index(year)
    games_node = ET.SubElement(root, "games")
    total = 0
    conf_counts = {}

    for week in range(1, max_weeks + 1):
        url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?seasontype=2&week={week}&year={year}"
        data = get_json(url)
        events = data.get("events") or []
        if not events:
            continue

        for game in events:
            try:
                gid = str(game.get("id") or "")
                date_str = iso_to_local_string(game.get("date"))
                competitions = game.get("competitions") or []
                if not competitions:
                    continue
                comp = competitions[0]
                competitors = comp.get("competitors") or []
                if len(competitors) < 2:
                    continue
                # ...existing code...
            except Exception as e:
                print(f"Error processing game: {e}")

                # Build team blocks with conference
                teams_elem = ET.Element("teams")
                home = {}
                away = {}

                for comp_team in competitors:
                    tinfo = comp_team.get("team") or {}
                    tid = str(tinfo.get("id") or "")
                    name = tinfo.get("displayName", "Unknown")
                    abbr = tinfo.get("abbreviation", "") or ""
                    location = tinfo.get("location", "") or ""
                    nickname = tinfo.get("name", "") or ""
                    logo = tinfo.get("logo", "") or ""
                    if not logo:
                        logos = tinfo.get("logos") or []
                        if logos:
                            logo = logos[0].get("href") or ""

                    conf = conf_index.get(tid)
                    if not conf:
                        # one-time backfill for this team
                        conf = cfb_backfill_team_conf(tid)

                    conf_counts[conf] = conf_counts.get(conf, 0) + 1

                    team_block = {
                        "name": name,
                        "abbreviation": abbr,
                        "location": location,
                        "nickname": nickname,
                        "conference": conf,
                        "logo": logo,
                        "score": comp_team.get("score") or "",
                        "record": ""
                    }

                    for rec in (comp_team.get("records") or []):
                        if rec.get("type") == "total":
                            team_block["record"] = rec.get("summary", "")
                            break

                    if comp_team.get("homeAway") == "home":
                        home = team_block
                    else:
                        away = team_block

                venue = (comp.get("venue") or {})
                address = venue.get("address") or {}
                stadium = venue.get("fullName") or "TBD"
                city = address.get("city", "")
                state = address.get("state", "")

                tv = "TBD"
                broadcasts = comp.get("broadcasts") or []
                if broadcasts:
                    media = broadcasts[0].get("media") or {}
                    tv = media.get("shortName", "TBD")

                status_desc = ((comp.get("status") or {}).get("type") or {}).get("description", "Scheduled")
                week_number = ((comp.get("week") or {}).get("number") or "")

                game_el = ET.SubElement(games_node, "game", id=gid)
                ET.SubElement(game_el, "date").text = date_str
                ET.SubElement(game_el, "status").text = status_desc
                ET.SubElement(game_el, "week").text = str(week_number)

                teams_container = ET.SubElement(game_el, "teams")

                # away
                away_el = ET.SubElement(teams_container, "away_team")
                for k in ["name","abbreviation","location","nickname","conference","logo","score","record"]:
                    ET.SubElement(away_el, k).text = str(away.get(k,""))

                # home
                home_el = ET.SubElement(teams_container, "home_team")
                for k in ["name","abbreviation","location","nickname","conference","logo","score","record"]:
                    ET.SubElement(home_el, k).text = str(home.get(k,""))

                venue_el = ET.SubElement(game_el, "venue")
                ET.SubElement(venue_el, "stadium").text = stadium
                ET.SubElement(venue_el, "city").text = city
                ET.SubElement(venue_el, "state").text = state

                broadcast_el = ET.SubElement(game_el, "broadcast")
                ET.SubElement(broadcast_el, "tv_channel").text = tv

                total += 1
            except Exception:
                continue

        time.sleep(0.25)

    summary = ET.SubElement(root, "summary")
    ET.SubElement(summary, "total_games").text = str(total)
    confs_el = ET.SubElement(summary, "conferences")
    for conf, count in sorted(conf_counts.items(), key=lambda x: (-x[1], x[0])):
        c = ET.SubElement(confs_el, "conference")
        c.set("name", conf)
        c.set("teams", str(count))

# ---------- NFL ----------

def nfl_build_division_index(year: int) -> dict:
    """
    Build {team_id: 'AFC South', etc.} from NFL standings to avoid any 'Independent'.
    """
    url = f"http://site.api.espn.com/apis/site/v2/sports/football/nfl/standings?season={year}"
    data = get_json(url)
    idx = {}

    def walk(node, nearest_div=None):
        name = node.get("name") or node.get("displayName") or node.get("shortName") or ""
        # NFL labels include 'AFC East', 'NFC South', etc.; just take them directly.
        new_nearest = name if ("afc" in name.lower() or "nfc" in name.lower()) else nearest_div

        standings = node.get("standings", {})
        for entry in standings.get("entries", []):
            team = entry.get("team", {})
            tid = str(team.get("id") or "")
            if tid and new_nearest:
                idx[tid] = new_nearest

        for child in node.get("children", []):
            walk(child, new_nearest)

    if data:
        walk(data, None)
        for child in data.get("children", []):
            walk(child, None)

    return idx

def build_nfl_section(root, year=2025, seasontype=2, max_weeks=18):
    """
    seasontype: 1=pre, 2=regular, 3=post
    """
    div_index = nfl_build_division_index(year)
    games_node = ET.SubElement(root, "games")
    total = 0
    div_counts = {}

    for week in range(1, max_weeks + 1):
        url = f"http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype={seasontype}&week={week}&year={year}"
        data = get_json(url)
        events = data.get("events") or []
        if not events:
            continue

        for game in events:
            try:
                gid = str(game.get("id") or "")
                date_str = iso_to_local_string(game.get("date"))
                competitions = game.get("competitions") or []
                if not competitions:
                    continue
                comp = competitions[0]
                competitors = comp.get("competitors") or []
                if len(competitors) < 2:
                    continue

                teams_elem = ET.Element("teams")
                home = {}
                away = {}

                for comp_team in competitors:
                    tinfo = comp_team.get("team") or {}
                    tid = str(tinfo.get("id") or "")
                    name = tinfo.get("displayName", "Unknown")
                    abbr = tinfo.get("abbreviation", "") or ""
                    location = tinfo.get("location", "") or ""
                    nickname = tinfo.get("name", "") or ""
                    logo = tinfo.get("logo", "") or ""
                    if not logo:
                        logos = tinfo.get("logos") or []
                        if logos:
                            logo = logos[0].get("href") or ""

                    division = div_index.get(tid, "Unknown")
                # ...existing code...
            except Exception as e:
                print(f"Error processing NFL game: {e}")
