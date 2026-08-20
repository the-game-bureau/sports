# Coach Steve Bot

The daily routine behind [Coach Steve's Sports Report](steve.html) and
[Kat's Sports Report](kat.html).

**Who it's for.** One reader: a man with Alzheimer's disease, reading on a phone, with
a short attention span. He should never have to click to find something out. Every
story is short, plain, and finished in two sentences.

**What it is.** A Claude routine — no scripts to run, no files to merge by hand.
Claude fetches the scores, researches the news, and writes the live and archive files
itself. The full instructions live in
[.claude/commands/coach-steve-bot.md](.claude/commands/coach-steve-bot.md); this page
is the summary.

---

## Running it

**In Claude Code:**

```text
/coach-steve-bot
```

That's the whole thing. It backs up both JSON files, pulls scores and schedules from
ESPN, researches each team's news, merges everything, archives the overflow, and tells
you what changed.

**On a schedule.** Ask Claude to run it daily and it becomes a cloud routine — the
report refreshes itself and you just reload the page. `/schedule` sets that up.

**Anywhere without file access** (claude.ai, the phone app): paste the contents of
[.claude/commands/coach-steve-bot.md](.claude/commands/coach-steve-bot.md) as your
prompt. Claude will do the research and hand back a complete `steve/steve.json` to paste
over the file.

---

## Two kinds of file

The data is split so the routine physically cannot clobber your work.

| File | Holds | Who writes it |
| --- | --- | --- |
| `steve/steve.json`, `kat/kat.json` | Teams, colors, logos, links, photos, hand-entered events | **You, by hand.** The routine only reads these. |
| `steve/steve_live.json`, `kat/kat_live.json` | Records, next games, last results, stories | The routine, every run |
| `steve/steve_archive.json`, `kat/kat_archive.json` | Stories that rolled off the front | The routine, every run |

The pages merge a report's two files at read time. Anything you set by hand — a
podcast button, a photo, an open practice — lives in a file the routine never opens
for writing, so a bad run cannot take it away.

This came from a real loss: an early run rebuilt a team object while writing news and
dropped The Current Radio Show from Kat's Tulane card.

## What it writes

Both reports run in one pass. Steve follows the Saints, Florida, Tulane, Texas, IUP,
and the Yankees; Kat follows the Saints, Florida, LSU, and Tulane. Shared teams are
researched once and written into both feeds.

| Field | Where it comes from |
| --- | --- |
| `record` | ESPN team endpoint |
| `nextGame` | ESPN schedule — first game not yet played, time converted to the venue's clock |
| `lastGame` | ESPN schedule — most recent completed game, with the score |
| `news[]` | Web research, **appended**, deduped by URL + headline |
| `meta.updated` | Today |

Newest 3 stories per team stay on the report. Older ones move to that report's archive
— `steve/steve_archive.json` behind [steve/steve_archive.html](steve/steve_archive.html), `kat/kat_archive.json`
behind [kat/kat_archive.html](kat/kat_archive.html).

Every run writes a `.bak` beside each file it touches, so a bad run is one file rename
away from undone.

---

## Things the routine knows that you might forget

- **ESPN 403s a faked user-agent.** It fingerprints the caller, so `curl` must send
  *no* `User-Agent` header at all — its own default passes, while `Mozilla/5.0` or a
  Chrome string gets denied. This is what broke the old `archive/games.py` path.
- **`team.nextEvent` can point at a game that already happened.** The routine reads
  the schedule and checks the date, so a past game is never shown as "next."
- **College schedules come back empty** from the plain call before the season opens;
  they need `?season=YYYY&seasontype=2`.
- **IUP is not in ESPN's API** — Division II volleyball isn't carried. Peyton
  Belcher's team is researched by hand every run, schedule and results included.
- **Streaming bundles are not TV.** A channel the reader's television actually
  receives wins over `MLB.TV` or `ESPN+`.

---

## Team ids

The routine uses whatever is in `steve/steve.json`; this is the current set.

| Team | id | ESPN |
| --- | --- | --- |
| Tulane Green Wave | `tulane` | football / college-football / 2655 |
| Florida Gators | `florida` | football / college-football / 57 |
| New Orleans Saints | `saints` | football / nfl / 18 |
| IUP Crimson Hawks | `iup` | *none — researched by hand* |
| LSU Tigers | `lsu` | football / college-football / 99 |
| New York Yankees | `yankees` | baseball / mlb / 10 |
| Texas Longhorns | `texas` | football / college-football / 251 |

To follow a new team, add an entry to `steve/steve.json` or `kat/kat.json` with its `espn` block,
`newsFocus`, and colors. To stop covering one, set `"hidden": true` — [steve.html](steve.html)
skips hidden teams and the routine leaves them alone.
