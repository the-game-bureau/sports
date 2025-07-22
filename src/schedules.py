import requests
from bs4 import BeautifulSoup
from jinja2 import Template
import xml.etree.ElementTree as ET

# STEP 1: Scrape all FBS teams from ESPN
teams_url = "https://www.espn.com/college-football/teams"
res = requests.get(teams_url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(res.text, "html.parser")

teams = []
for section in soup.select("section.TeamLinks"):
    anchor = section.select_one("a.AnchorLink")
    if not anchor: continue
    name = anchor.text.strip()
    href = anchor["href"]
    # /college-football/team/_/id/239/tulane-green-wave
    try:
        parts = href.split("/id/")[1].split("/")
        team_id = parts[0]
        slug = parts[1]
        teams.append({
            "name": name,
            "id": team_id,
            "slug": slug,
            "url": f"https://www.espn.com/college-football/team/schedule/_/id/{team_id}"
        })
    except IndexError:
        continue

# STEP 2: Save to XML
root = ET.Element("teams")
for t in teams:
    team = ET.SubElement(root, "team")
    ET.SubElement(team, "name").text = t["name"]
    ET.SubElement(team, "id").text = t["id"]
    ET.SubElement(team, "slug").text = t["slug"]
    ET.SubElement(team, "url").text = t["url"]

tree = ET.ElementTree(root)
tree.write("fbs_teams.xml", encoding="utf-8", xml_declaration=True)

print("✅ fbs_teams.xml created with all FBS teams.")

# STEP 3: Find Tulane
tulane = next(t for t in teams if "tulane" in t["slug"].lower())
schedule_url = tulane["url"]

# STEP 4: Scrape Tulane’s Schedule
res = requests.get(schedule_url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(res.text, "html.parser")

games = []
rows = soup.select("table tbody tr")

for row in rows:
    cells = row.find_all("td")
    if len(cells) < 3:
        continue
    date = cells[0].get_text(strip=True)
    opponent = cells[1].get_text(strip=True).replace("vs", "").replace("@", "").strip()
    location = "home" if "vs" in cells[1].text else "away"
    result = cells[2].get_text(strip=True) if len(cells) > 2 else ""
    time = cells[3].get_text(strip=True) if len(cells) > 3 else "TBD"
    network = cells[4].get_text(strip=True) if len(cells) > 4 else "--"
    games.append({
        "date": date,
        "opponent": opponent,
        "location": location,
        "result": result,
        "time": time,
        "network": network
    })

# STEP 5: Output Tulane’s Schedule to HTML
html_tmpl = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Tulane Football 2025</title>
<style>
  body { font-family: sans-serif; background: #f0f0f0; padding: 2rem; }
  .game { margin-bottom: 1rem; padding: 1rem; background: #fff; border-left: 6px solid #00754a; }
  .away { border-left-color: #999; background: #f9f9f9; }
  .label { font-weight: bold; display: inline-block; width: 80px; }
</style>
</head>
<body>
<h1>Tulane Green Wave – 2025 Schedule</h1>
{% for g in games %}
<div class="game {{ g.location }}">
  <div><span class="label">Date:</span> {{ g.date }}</div>
  <div><span class="label">Opponent:</span> {{ g.opponent }}</div>
  <div><span class="label">Time:</span> {{ g.time }}</div>
  <div><span class="label">Network:</span> {{ g.network }}</div>
</div>
{% endfor %}
</body>
</html>
"""

with open("tulane_schedule.html", "w", encoding="utf-8") as f:
    f.write(Template(html_tmpl).render(games=games))

print("✅ tulane_schedule.html created.")
