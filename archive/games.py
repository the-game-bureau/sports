#!/usr/bin/env python3
# games.py — build an NFL games.xml from ESPN's public scoreboard API (default season: 2025)
#
# Examples:
#   python games.py                       # builds 2025 REG+POST
#   python games.py --season 2005         # builds 2005 REG+POST
#   python games.py --teams teams.xml     # filter to NFL teams in teams.xml
#   python games.py --out data/games.xml  # custom output path
#
# Notes:
# - Regular season is seasontype=2, weeks 1..18 (we stop at the first empty week).
# - Postseason is seasontype=3, weeks 1..(stop at first empty).
# - ESPN endpoint pattern:
#   https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?year=YYYY&seasontype=T&week=W
#
# Fields captured per game:
#   season_type (REG/POST), week, date (ISO), time (from ISO), away, home,
#   pts_away, pts_home, overtime (Y/N), espn_event_id, espn_gamecast_url

import sys
import re
import argparse
import time
from typing import List, Dict, Optional, Set
import requests
import xml.etree.ElementTree as ET

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
TIMEOUT = 30

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Origin": "https://www.espn.com",
        "Referer": "https://www.espn.com/nfl/scoreboard"
    })
    return s

def fetch_week(sess: requests.Session, year: int, seasontype: int, week: int) -> dict:
    params = {"year": year, "seasontype": seasontype, "week": week}
    r = sess.get(BASE_URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def load_team_filter(path: str) -> Optional[Set[str]]:
    """Load NFL team names from teams.xml to use as a filter (case-insensitive)."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        names: Set[str] = set()
        for team in root.iter("team"):
            league = (team.findtext("league") or team.findtext("league_abbr") or "").strip()
            if league not in {"NFL", "National Football League (NFL)"}:
                continue
            name = (team.findtext("name") or "").strip()
            if name:
                names.add(norm(name))
        if names:
            print(f"[teams.xml] Loaded {len(names)} NFL team names for filtering.", file=sys.stderr)
            return names
    except Exception as e:
        print(f"[teams.xml] Warning: failed to read '{path}': {e}", file=sys.stderr)
    return None

def parse_event(ev: dict) -> Dict[str, str]:
    """Flatten one ESPN 'event' to our normalized dict."""
    eid = str(ev.get("id", ""))

    date_iso = ev.get("date", "")  # e.g., "2025-09-07T17:00Z"
    # Separate time for compatibility (keep original ISO in <date> too)
    time_part = ""
    if "T" in date_iso:
        time_part = date_iso.split("T", 1)[1]

    comp = (ev.get("competitions") or [{}])[0]
    comps = comp.get("competitors") or []
    home_name = away_name = ""
    home_score = away_score = ""
    ot_flag = ""

    for c in comps:
        team = (c.get("team") or {})
        nm = team.get("displayName") or team.get("name") or ""
        if c.get("homeAway") == "home":
            home_name = nm
            home_score = str(c.get("score") or "")
        elif c.get("homeAway") == "away":
            away_name = nm
            away_score = str(c.get("score") or "")

    # Overtime: check status / details
    status = comp.get("status") or {}
    typeobj = status.get("type") or {}
    # ESPN often includes "OT" in shortDetail or "period" > 4
    short_detail = (status.get("type") or {}).get("shortDetail", "") or status.get("shortDetail", "")
    period = (status.get("period") or 0)
    if "OT" in (short_detail or "") or (isinstance(period, int) and period > 4):
        ot_flag = "Y"

    # Build Gamecast URL
    gamecast_url = f"https://www.espn.com/nfl/game/_/gameId/{eid}" if eid else ""

    # Week/seasontype are returned at the top-level 'week' object sometimes; trust caller to inject week/seasontype later.
    return {
        "date": date_iso,
        "time": time_part,
        "away": away_name,
        "home": home_name,
        "pts_away": away_score,
        "pts_home": home_score,
        "overtime": ot_flag,
        "espn_event_id": eid,
        "espn_gamecast_url": gamecast_url,
    }

def collect_season(sess: requests.Session, year: int) -> List[Dict[str, str]]:
    """Fetch all regular-season and postseason games for a season."""
    all_games: List[Dict[str, str]] = []

    def harvest(seasontype: int, label: str, max_weeks_guess: int) -> None:
        week = 1
        empty_streak = 0
        while True:
            try:
                data = fetch_week(sess, year, seasontype, week)
            except requests.HTTPError as e:
                # If ESPN hasn't populated a future week yet, break cleanly
                print(f"[{label}] HTTP {e.response.status_code} for week {week}; stopping this season type.", file=sys.stderr)
                break

            events = data.get("events") or []
            if not events:
                empty_streak += 1
                # Two empties in a row -> stop (handles gaps/future weeks)
                if empty_streak >= 2:
                    break
                week += 1
                continue

            empty_streak = 0
            for ev in events:
                g = parse_event(ev)
                g["season_type"] = "REG" if seasontype == 2 else "POST"
                g["week"] = str(week)
                all_games.append(g)

            print(f"[{label}] Week {week}: +{len(events)} games (total {len(all_games)}).", file=sys.stderr)

            week += 1
            # safety valve
            if week > max_weeks_guess:
                break
            time.sleep(0.25)  # be polite

    # Regular season: up to 20 just in case (bye flex / intl adjustments)
    harvest(seasontype=2, label="REG", max_weeks_guess=20)
    # Postseason: up to 6 (WC, DIV, CONF, SB; sometimes Pro Bowl exists under other seasontype)
    harvest(seasontype=3, label="POST", max_weeks_guess=6)

    return all_games

def filter_by_teams(games: List[Dict[str, str]], allow: Optional[Set[str]]) -> List[Dict[str, str]]:
    if not allow:
        return games
    kept: List[Dict[str, str]] = []
    for g in games:
        if norm(g["away"]) in allow or norm(g["home"]) in allow:
            kept.append(g)
    print(f"[filter] Kept {len(kept)} of {len(games)} games after team filter.", file=sys.stderr)
    return kept

def write_games_xml(games: List[Dict[str, str]], year: int, out_path: str) -> None:
    root = ET.Element("games")

    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "generated_by").text = "games.py"
    ET.SubElement(meta, "source").text = BASE_URL
    ET.SubElement(meta, "season").text = str(year)
    ET.SubElement(meta, "generated_at").text = time.strftime("%Y-%m-%dT%H:%M:%S")

    def add(parent, tag, text):
        el = ET.SubElement(parent, tag)
        el.text = text or ""
        return el

    for g in games:
        game = ET.SubElement(root, "game")
        add(game, "season_type", g.get("season_type"))
        add(game, "week", g.get("week"))
        add(game, "date", g.get("date"))
        add(game, "time", g.get("time"))
        add(game, "away", g.get("away"))
        add(game, "home", g.get("home"))
        add(game, "pts_away", g.get("pts_away"))
        add(game, "pts_home", g.get("pts_home"))
        add(game, "overtime", g.get("overtime"))
        add(game, "espn_event_id", g.get("espn_event_id"))
        add(game, "espn_gamecast_url", g.get("espn_gamecast_url"))

    try:
        ET.indent(root, space="  ")
    except Exception:
        pass

    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {out_path} with {len(games)} games.", file=sys.stderr)

def main():
    ap = argparse.ArgumentParser(description="Build an NFL games.xml from ESPN for a given season.")
    ap.add_argument("--season", type=int, default=2025, help="Season year (default: 2025)")
    ap.add_argument("--teams", help="Optional teams.xml filter (NFL only).", default=None)
    ap.add_argument("--out", help="Output path (default: games.xml)", default="games.xml")
    args = ap.parse_args()

    sess = build_session()

    team_filter: Optional[Set[str]] = None
    if args.teams:
        team_filter = load_team_filter(args.teams)

    games = collect_season(sess, args.season)
    if team_filter:
        games = filter_by_teams(games, team_filter)

    write_games_xml(games, args.season, args.out)

if __name__ == "__main__":
    main()
