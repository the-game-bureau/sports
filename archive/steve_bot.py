#!/usr/bin/env python3
"""Coach Steve Bot — merge a news update into steve.json.

Takes the JSON that Coach Steve Bot produces (see coach_steve_bot.md) and folds
it into steve.json: new stories are appended, duplicates are dropped, and
anything past the per-team limit is retired to steve_archive.json.

Usage:
    python steve_bot.py update.json        # merge a file
    python steve_bot.py                    # paste the JSON, then Ctrl+Z Enter (Windows)
    python steve_bot.py --prune            # just re-run the archive trim
    python steve_bot.py update.json --dry-run

The update format (extra keys are ignored, every field is optional):

    {
      "generated": "2026-08-19",
      "teams": {
        "iup": {
          "record": "3-1",
          "nextGame": {"homeAway": "home", "opponent": "Slippery Rock",
                       "date": "2026-08-29", "time": "7:00 PM",
                       "venue": "Memorial Field House", "city": "Indiana, PA",
                       "tv": {"name": "PSAC TV", "logo": "", "url": ""}},
          "lastGame": {"result": "W", "teamScore": 3, "opponentScore": 1,
                       "opponent": "Gannon", "date": "2026-08-26"},
          "news": [
            {"headline": "Peyton Belcher named PSAC Player of the Week",
             "summary": "She had 18 kills in the win over Gannon.",
             "date": "2026-08-27",
             "source": "IUP Athletics",
             "url": "https://iupathletics.com/news/..."}
          ]
        }
      }
    }
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PATH = os.path.join(HERE, "steve.json")
ARCHIVE_PATH = os.path.join(HERE, "steve_archive.json")

# How many stories stay on the front page per team. The reader has a short
# attention span — three is already generous.
MAX_NEWS_PER_TEAM = 3
# Hard cap so the archive file cannot grow forever.
MAX_ARCHIVE_ITEMS = 500


# ---------------------------------------------------------------- io helpers

def load_json(path, default=None):
    if not os.path.exists(path):
        if default is None:
            sys.exit("Missing file: %s" % path)
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    if os.path.exists(path):
        backup = path + ".bak"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
    os.replace(tmp, path)


def read_update(source):
    """Read the update JSON, tolerating a ```json fence around it."""
    text = source.read() if hasattr(source, "read") else source
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text:
        sys.exit("No update JSON given.")
    try:
        return json.loads(text)
    except ValueError as exc:
        sys.exit("That is not valid JSON: %s" % exc)


# ------------------------------------------------------------- news plumbing

def story_id(item):
    """Stable id so the same story never lands twice."""
    if item.get("id"):
        return str(item["id"])
    seed = (item.get("url") or "") + "|" + (item.get("headline") or "")
    return hashlib.sha1(seed.strip().lower().encode("utf-8")).hexdigest()[:12]


def normalize_story(item, team_id):
    out = {
        "id": story_id(item),
        "teamId": team_id,
        "headline": (item.get("headline") or "").strip(),
        "summary": (item.get("summary") or "").strip(),
        "date": (item.get("date") or "").strip(),
        "source": (item.get("source") or "").strip(),
        "url": (item.get("url") or "").strip(),
    }
    return out


def newest_first(items):
    return sorted(items, key=lambda i: (i.get("date") or "", i.get("headline") or ""), reverse=True)


def teams_from_update(update):
    """Accept either {"teams": {"id": {...}}} or {"teams": [{"id": ...}]}."""
    teams = update.get("teams", update)
    if isinstance(teams, list):
        return {t.get("id"): t for t in teams if t.get("id")}
    if isinstance(teams, dict):
        return teams
    return {}


# ------------------------------------------------------------------- merging

def merge(main, archive, update, report):
    incoming = teams_from_update(update)
    known = {t.get("id"): t for t in main.get("teams", [])}

    archive_items = archive.setdefault("items", [])
    seen_ids = set(story_id(i) for i in archive_items)
    for team in main.get("teams", []):
        for item in team.get("news", []) or []:
            seen_ids.add(story_id(item))

    for team_id, patch in incoming.items():
        team = known.get(team_id)
        if team is None:
            report.append("  ? unknown team '%s' — skipped" % team_id)
            continue
        if not isinstance(patch, dict):
            continue

        # Scalar/state fields only overwrite when the bot actually supplies them.
        for field in ("record", "nextGame", "lastGame"):
            if field in patch and patch[field] is not None:
                team[field] = patch[field]
                report.append("  %s: %s updated" % (team_id, field))

        added = 0
        stories = team.get("news") or []
        for raw in patch.get("news") or []:
            item = normalize_story(raw, team_id)
            if not item["headline"]:
                continue
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            stories.append(item)
            added += 1
        team["news"] = newest_first(stories)
        if added:
            report.append("  %s: +%d %s" % (team_id, added, "story" if added == 1 else "stories"))

    return main, archive


def prune(main, archive, report):
    """Move anything past the per-team limit into the archive."""
    archive_items = archive.setdefault("items", [])
    archived_ids = set(story_id(i) for i in archive_items)
    moved = 0

    for team in main.get("teams", []):
        stories = newest_first(team.get("news") or [])
        keep, overflow = stories[:MAX_NEWS_PER_TEAM], stories[MAX_NEWS_PER_TEAM:]
        team["news"] = keep
        for item in overflow:
            item.setdefault("teamId", team.get("id"))
            if story_id(item) not in archived_ids:
                archived_ids.add(story_id(item))
                archive_items.append(item)
                moved += 1

    archive["items"] = newest_first(archive_items)[:MAX_ARCHIVE_ITEMS]
    if moved:
        report.append("  archived %d older %s" % (moved, "story" if moved == 1 else "stories"))
    return main, archive


# ---------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Merge a Coach Steve Bot update into steve.json.")
    ap.add_argument("update", nargs="?", help="path to the update JSON (omit to read stdin)")
    ap.add_argument("--prune", action="store_true", help="only re-run the archive trim")
    ap.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = ap.parse_args(argv)

    main_data = load_json(MAIN_PATH)
    archive_data = load_json(ARCHIVE_PATH, {
        "meta": {
            "title": "Coach Steve's Story Archive",
            "byline": main_data.get("meta", {}).get("byline", ""),
            "updated": None,
            "note": "Older stories moved out of steve.json by Coach Steve Bot. Newest first.",
        },
        "items": [],
    })

    report = []
    stamp = datetime.date.today().isoformat()

    if not args.prune:
        if args.update:
            with open(args.update, "r", encoding="utf-8") as fh:
                update = read_update(fh)
        else:
            if sys.stdin.isatty():
                print("Paste the Coach Steve Bot JSON, then press Ctrl+Z and Enter:\n")
            update = read_update(sys.stdin)
        stamp = (update.get("generated") or stamp).strip()[:10]
        main_data, archive_data = merge(main_data, archive_data, update, report)

    main_data, archive_data = prune(main_data, archive_data, report)

    main_data.setdefault("meta", {})["updated"] = stamp
    archive_data.setdefault("meta", {})["updated"] = stamp

    if not report:
        report.append("  nothing new")

    print("Coach Steve Bot — %s" % stamp)
    for line in report:
        print(line)

    if args.dry_run:
        print("\n(dry run — no files written)")
        return 0

    save_json(MAIN_PATH, main_data)
    save_json(ARCHIVE_PATH, archive_data)
    print("\nWrote steve.json and steve_archive.json (previous copies saved as .bak).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
