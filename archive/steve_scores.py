#!/usr/bin/env python3
"""Coach Steve Bot — scores half.

Pulls record, next game, and last result straight from ESPN's public API into
steve.json. No model involved: schedules and scores are facts, so a script does
them. Coach Steve Bot's model half (coach_steve_bot.md) only writes the news.

Usage:
    python steve_scores.py                 # refresh every team that has an "espn" block
    python steve_scores.py --team yankees  # just one
    python steve_scores.py --dry-run       # show what would change, write nothing

Teams without an "espn" block in steve.json (IUP is Division II and not carried
by ESPN) are skipped and left for the model to fill in.

Replaces the old games.py / teams.py path: those built league-wide XML dumps of a
hardcoded season. This asks ESPN only about the six teams on the page and writes
the answer where the page actually reads it.
"""

import argparse
import datetime
import json
import os
import sys

try:
    import requests
except ImportError:
    sys.exit("This needs the requests package: pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PATH = os.path.join(HERE, "steve.json")

API = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}"
TIMEOUT = 25

# Venue local time. ESPN hands back UTC and no timezone, so map the venue's state.
EASTERN = {"CT","DE","FL","GA","IN","KY","ME","MD","MA","MI","NH","NJ","NY","NC","OH","PA","RI","SC","VT","VA","WV","DC"}
CENTRAL = {"AL","AR","IL","IA","KS","LA","MN","MS","MO","NE","ND","OK","SD","TN","TX","WI"}
MOUNTAIN = {"CO","ID","MT","NM","UT","WY"}
PACIFIC = {"CA","NV","OR","WA"}
NO_DST = {"AZ": -7, "HI": -10}

STATE_ABBR = {
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO",
    "connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID",
    "illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA",
    "maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN",
    "mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV",
    "new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY",
    "north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR",
    "pennsylvania":"PA","rhode island":"RI","south carolina":"SC","south dakota":"SD",
    "tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA",
    "washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY",
    "district of columbia":"DC",
}


# ------------------------------------------------------------------ time math

def _nth_sunday(year, month, nth):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)   # first Sunday
    return d + datetime.timedelta(weeks=nth - 1)


def _is_dst(utc_dt):
    """US rule: second Sunday in March 2am to first Sunday in November 2am."""
    y = utc_dt.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7))   # 2am ET in UTC
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6))
    return start <= utc_dt < end


def state_code(address):
    raw = (address or {}).get("state") or ""
    raw = raw.strip()
    if len(raw) == 2:
        return raw.upper()
    return STATE_ABBR.get(raw.lower(), "")


def to_local(iso_utc, address):
    """ESPN's UTC stamp -> (YYYY-MM-DD, '7:05 PM') at the venue."""
    if not iso_utc:
        return None, None
    try:
        utc = datetime.datetime.strptime(iso_utc.replace("Z", ""), "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            utc = datetime.datetime.strptime(iso_utc.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None, None

    st = state_code(address)
    if st in NO_DST:
        offset = NO_DST[st]
    else:
        if st in CENTRAL:
            base = -6
        elif st in MOUNTAIN:
            base = -7
        elif st in PACIFIC:
            base = -8
        elif st in EASTERN or not st:
            base = -5
        else:
            base = -5
        offset = base + (1 if _is_dst(utc) else 0)

    local = utc + datetime.timedelta(hours=offset)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return local.strftime("%Y-%m-%d"), "%d:%02d %s" % (hour, local.minute, ampm)


# -------------------------------------------------------------- espn plumbing

def session():
    s = requests.Session()
    # ESPN 403s the full Chrome user-agent string (the one games.py sends).
    # A bare "Mozilla/5.0" is what it actually answers.
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"})
    return s


def get_json(sess, url, params=None):
    r = sess.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def score_of(competitor):
    s = competitor.get("score")
    if isinstance(s, dict):
        s = s.get("value")
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def sides(competition, team_id):
    """Split a competition into (us, them)."""
    us = them = None
    for c in competition.get("competitors", []):
        if str((c.get("team") or {}).get("id")) == str(team_id):
            us = c
        else:
            them = c
    return us, them


def pick_broadcast(competition, existing_tv):
    """Prefer a channel a normal TV gets over a streaming bundle."""
    names = []
    for b in competition.get("broadcasts") or []:
        media = (b.get("media") or {}).get("shortName")
        if media:
            names.append(media)
        for n in b.get("names") or []:
            names.append(n)
    if not names:
        return None

    junk = ("mlb.tv", "espn+", "espn unlmtd", "prime video", "peacock", "paramount+")
    preferred = [n for n in names if n.lower() not in junk] or names
    name = preferred[0]

    tv = {"name": name, "logo": "", "url": ""}
    # Keep the logo/url the page already had if the channel did not change.
    if existing_tv and existing_tv.get("name", "").lower() == name.lower():
        tv["logo"] = existing_tv.get("logo", "")
        tv["url"] = existing_tv.get("url", "")
    return tv


def next_game(event, team_id, existing_tv):
    comp = (event.get("competitions") or [{}])[0]
    venue = comp.get("venue") or {}
    address = venue.get("address") or {}
    us, them = sides(comp, team_id)
    if them is None:
        return None

    date, time_str = to_local(event.get("date"), address)
    city = ", ".join([p for p in [address.get("city"), state_code(address)] if p])

    game = {
        "homeAway": (us or {}).get("homeAway") or "home",
        "opponent": (them.get("team") or {}).get("displayName") or "",
        "date": date,
        "time": time_str,
        "venue": venue.get("fullName") or "",
        "city": city,
    }
    tv = pick_broadcast(comp, existing_tv)
    if tv:
        game["tv"] = tv
    return game


def fetch_events(sess, sport, league, team_id):
    """Every event ESPN will give us for this team, this season.

    The bare /schedule call returns the current season type — which for an NFL
    team in August is preseason, and for a college team is empty. Fall back to
    an explicit regular-season request so the college teams come back too.
    """
    url = API.format(sport=sport, league=league, team_id=team_id) + "/schedule"
    year = datetime.date.today().year
    attempts = [None, {"season": year, "seasontype": 2}]

    events = []
    for params in attempts:
        try:
            data = get_json(sess, url, params)
        except Exception:
            continue
        for event in data.get("events") or []:
            events.append(event)
        if params is None and events:
            # Preseason results are real results; keep them and add the regular
            # season on the next pass so "next game" skips past exhibitions.
            continue
    # Same event can arrive twice across the two calls.
    seen, unique = set(), []
    for event in events:
        key = event.get("id") or event.get("date")
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    unique.sort(key=lambda e: e.get("date") or "")
    return unique


def is_completed(event):
    comp = (event.get("competitions") or [{}])[0]
    return bool((((comp.get("status") or {}).get("type")) or {}).get("completed"))


def last_game(events, team_id):
    done = [e for e in events if is_completed(e)]
    if not done:
        return None

    event = done[-1]
    comp = (event.get("competitions") or [{}])[0]
    us, them = sides(comp, team_id)
    if not us or not them:
        return None

    address = (comp.get("venue") or {}).get("address") or {}
    date, _ = to_local(event.get("date"), address)
    return {
        "result": "W" if us.get("winner") else "L",
        "teamScore": score_of(us),
        "opponentScore": score_of(them),
        "opponent": (them.get("team") or {}).get("displayName") or "",
        "date": date,
    }


def upcoming(events):
    """First game that has not happened yet — never a past one."""
    today = datetime.date.today().isoformat()
    for event in events:
        if is_completed(event):
            continue
        if (event.get("date") or "")[:10] >= today:
            return event
    return None


def record_of(team):
    for item in (team.get("record") or {}).get("items") or []:
        if item.get("summary"):
            return item["summary"]
    return None


# ---------------------------------------------------------------------- main

def refresh(team, sess, report):
    cfg = team.get("espn")
    if not cfg or not cfg.get("teamId"):
        report.append("  %s: no ESPN id — left for the news bot" % team["id"])
        return False

    url = API.format(sport=cfg["sport"], league=cfg["league"], team_id=cfg["teamId"])
    try:
        payload = get_json(sess, url).get("team") or {}
    except Exception as exc:
        report.append("  %s: ESPN lookup failed (%s)" % (team["id"], exc))
        return False

    changed = []

    rec = record_of(payload)
    if rec and rec != team.get("record"):
        team["record"] = rec
        changed.append("record " + rec)

    events = fetch_events(sess, cfg["sport"], cfg["league"], cfg["teamId"])

    # Prefer the schedule; fall back to ESPN's nextEvent, but never write a
    # game whose date has already passed.
    event = upcoming(events)
    if event is None:
        candidate = (payload.get("nextEvent") or [None])[0]
        today = datetime.date.today().isoformat()
        if candidate and (candidate.get("date") or "")[:10] >= today:
            event = candidate

    if event is not None:
        existing_tv = (team.get("nextGame") or {}).get("tv")
        game = next_game(event, cfg["teamId"], existing_tv)
        if game and game != team.get("nextGame"):
            team["nextGame"] = game
            word = "at" if game["homeAway"] == "away" else "vs"
            changed.append("next %s %s on %s" % (word, game["opponent"], game["date"]))

    last = last_game(events, cfg["teamId"])
    if last and last != team.get("lastGame"):
        team["lastGame"] = last
        changed.append("last %s %s-%s" % (last["result"], last["teamScore"], last["opponentScore"]))

    report.append("  %s: %s" % (team["id"], ", ".join(changed) if changed else "already current"))
    return bool(changed)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Refresh steve.json scores and schedules from ESPN.")
    ap.add_argument("--team", help="only this team id")
    ap.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    args = ap.parse_args(argv)

    with open(MAIN_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    sess = session()
    report = []
    touched = False

    for team in data.get("teams", []):
        if args.team and team.get("id") != args.team:
            continue
        touched = refresh(team, sess, report) or touched

    print("Coach Steve Bot — scores")
    for line in report or ["  no teams matched"]:
        print(line)

    if args.dry_run:
        print("\n(dry run — no files written)")
        return 0

    if not touched:
        print("\nNothing changed; steve.json left alone.")
        return 0

    data.setdefault("meta", {})["updated"] = datetime.date.today().isoformat()

    backup = MAIN_PATH + ".bak"
    if os.path.exists(backup):
        os.remove(backup)
    os.replace(MAIN_PATH, backup)
    with open(MAIN_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("\nWrote steve.json (previous copy saved as steve.json.bak).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
