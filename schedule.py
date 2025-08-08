import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
import time
import json

def debug_api_structure():
    """Comprehensive debug function to understand ESPN API structure"""
    print("=== DEBUGGING ESPN API STRUCTURE ===")

    # Try recent completed games first (2024 season)
    url = "http://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?seasontype=2&week=1&year=2024"

    try:
        response = requests.get(url, timeout=20)
        data = response.json()

        if 'events' in data and data['events']:
            game = data['events'][0]
            print(f"Sample game ID: {game.get('id')}")

            competitors = game['competitions'][0]['competitors']

            for i, competitor in enumerate(competitors):
                team_info = competitor['team']
                team_name = team_info.get('displayName', 'Unknown')

                print(f"\n--- TEAM {i+1}: {team_name} ---")
                print("All team_info keys:", sorted(team_info.keys()))

                # Print the entire team structure for first team
                if i == 0:
                    print("\nFULL TEAM STRUCTURE:")
                    pretty = json.dumps(team_info, indent=2)
                    print(pretty[:2000] + "..." if len(pretty) > 2000 else pretty)

                # Look for conference-related fields
                conference_fields = [k for k in team_info.keys() if 'conf' in k.lower() or 'league' in k.lower() or 'group' in k.lower()]
                if conference_fields:
                    print(f"Conference-related fields: {conference_fields}")
                    for field in conference_fields:
                        print(f"  {field}: {team_info[field]}")

                # Check groups structure
                if 'groups' in team_info:
                    print(f"Groups structure: {team_info['groups']}")

                # Check if there's any nested structure
                for key, value in team_info.items():
                    if isinstance(value, dict) and any(conf_key in str(value).lower() for conf_key in ['conference', 'league', 'division']):
                        print(f"Nested structure in '{key}': {value}")

                print("-" * 50)

    except Exception as e:
        print(f"Debug error: {e}")

def get_team_details_from_api(team_id):
    """Get detailed team info from ESPN team API (fallback; standings map is preferred)."""
    try:
        team_url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{team_id}"
        response = requests.get(team_url, timeout=20)
        data = response.json()

        if 'team' in data:
            team = data['team']
            # Look for conference in team details
            if 'groups' in team:
                for group in team['groups']:
                    if 'name' in group and 'Conference' in group.get('name', ''):
                        return group['name'], group.get('id', '')

            # Check other possible locations
            if 'conference' in team:
                conf = team['conference']
                if isinstance(conf, dict):
                    return conf.get('name', 'Independent'), conf.get('id', '')
                return str(conf), ''

        return 'Independent', ''
    except Exception:
        return 'Independent', ''

def build_conference_index(year: int) -> dict:
    """
    Build a {team_id: conference_name} map using the standings tree for the season.
    This is the authoritative way to get conferences per ESPN.
    """
    url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/standings?season={year}"
    idx = {}

    try:
        data = requests.get(url, timeout=30).json()
    except Exception:
        return idx

    conf_indicators = [
        "Conference", "SEC", "ACC", "Big ", "Pac", "Sun Belt",
        "Mountain West", "American", "AAC", "MAC", "Conference USA",
        "SWAC", "MEAC", "Valley", "OVC", "SoCon", "Ivy", "Patriot",
        "Pioneer", "Big Sky", "CAA", "WAC", "ASUN", "United Athletic",
        "Independents", "Independent", "FBS Independents", "FCS Independents"
    ]

    def looks_like_conference(name: str) -> bool:
        n = (name or "").strip()
        if not n:
            return False
        n_low = n.lower()
        return any(k.lower() in n_low for k in conf_indicators)

    def walk(node, current_conf=None):
        node_name = node.get("name") or node.get("shortName") or node.get("displayName")
        conf_here = node_name if node_name and looks_like_conference(node_name) else current_conf

        # Map teams under this node's standings to the active conference
        standings = node.get("standings", {})
        for entry in standings.get("entries", []):
            team = entry.get("team", {})
            tid = team.get("id")
            if tid and conf_here:
                idx[str(tid)] = node_name  # store raw name; we'll normalize later

        # Recurse into children
        for child in node.get("children", []):
            walk(child, conf_here)

    # The API sometimes nests under root and/or 'children'
    walk(data)
    for child in data.get("children", []):
        walk(child)

    return idx

def normalize_conference_name(conf_name):
    """Normalize and rollup conference names to handle variations and recent changes"""
    if not conf_name or conf_name.lower().strip() in {'independent', 'independents', 'fbs independents', 'fcs independents'}:
        return 'Independent'

    conf_lower = conf_name.lower()

    # American Conference (formerly AAC) variations and rollup
    if any(term in conf_lower for term in ['american athletic', 'american conference', 'aac', 'the american']):
        return 'American Athletic Conference'

    # Power conferences
    if any(term in conf_lower for term in ['southeastern', 'sec']):
        return 'SEC'

    if any(term in conf_lower for term in ['big ten', 'big 10', 'b1g']):
        return 'Big Ten'

    if any(term in conf_lower for term in ['atlantic coast', 'acc']):
        return 'ACC'

    if any(term in conf_lower for term in ['big 12', 'big twelve']):
        return 'Big 12'

    if any(term in conf_lower for term in ['pac-12', 'pac 12', 'pacific-12', 'pacific 12', 'pac']):
        # For legacy data still labeling Pac-12/“Pac”
        return 'Pac-12'

    # Group of 5 Conference rollups
    if any(term in conf_lower for term in ['mountain west', 'mwc']):
        return 'Mountain West'

    if any(term in conf_lower for term in ['conference usa', 'c-usa', 'cusa']):
        return 'Conference USA'

    if any(term in conf_lower for term in ['mid-american', 'mac']):
        return 'MAC'

    if 'sun belt' in conf_lower:
        return 'Sun Belt'

    # FCS Conference rollups
    if 'ivy' in conf_lower:
        return 'Ivy League'

    if 'patriot' in conf_lower:
        return 'Patriot League'

    if 'colonial athletic' in conf_lower or 'caa' in conf_lower:
        return 'Colonial Athletic Association'

    if 'big sky' in conf_lower:
        return 'Big Sky'

    if 'missouri valley' in conf_lower or 'mvfc' in conf_lower:
        return 'Missouri Valley Football Conference'

    if 'southland' in conf_lower:
        return 'Southland Conference'

    if 'ohio valley' in conf_lower or 'ovc' in conf_lower:
        return 'Ohio Valley Conference'

    if 'southern conference' in conf_lower or 'socon' in conf_lower:
        return 'Southern Conference'

    if 'big south' in conf_lower:
        return 'Big South Conference'

    if 'northeast conference' in conf_lower or 'nec' in conf_lower:
        return 'Northeast Conference'

    if 'pioneer football' in conf_lower or conf_lower.strip() == 'pioneer':
        return 'Pioneer Football League'

    if 'meac' in conf_lower:
        return 'MEAC'

    if 'swac' in conf_lower:
        return 'SWAC'

    # Newer/edge labels you might see in standings
    if 'united athletic' in conf_lower or 'uac' in conf_lower:
        return 'United Athletic Conference'

    # Independent variations
    if 'independent' in conf_lower:
        return 'Independent'

    # Return original if no match found
    return conf_name

def get_conference_info_enhanced(team_info, competitor_data=None):
    """
    Enhanced conference detection with multiple strategies.
    Now secondary (first try standings map in create_xml).
    """
    # Strategy 1: Direct conference field
    if 'conference' in team_info:
        conf = team_info['conference']
        if isinstance(conf, dict):
            name = conf.get('name', conf.get('displayName', ''))
            if name and name != 'Independent':
                normalized = normalize_conference_name(name)
                return normalized, conf.get('id', '')
        elif isinstance(conf, str) and conf != 'Independent':
            normalized = normalize_conference_name(conf)
            return normalized, ''

    # Strategy 2: Groups analysis - look for conference-like groups
    if 'groups' in team_info and team_info['groups']:
        for group in team_info['groups']:
            group_name = group.get('name', '')
            if any(indicator in group_name for indicator in ['Conference', 'Athletic', 'Big', 'Pac', 'SEC', 'ACC', 'American']):
                normalized = normalize_conference_name(group_name)
                return normalized, group.get('id', '')
            if 'parent' in group and 'name' in group['parent']:
                parent_name = group['parent']['name']
                if any(indicator in parent_name for indicator in ['Conference', 'Athletic', 'Big', 'Pac', 'SEC', 'ACC']):
                    normalized = normalize_conference_name(parent_name)
                    return normalized, group['parent'].get('id', '')

    # Strategy 3: Check competitor-level data
    if competitor_data and 'conference' in competitor_data:
        conf = competitor_data['conference']
        if isinstance(conf, dict):
            name = conf.get('name', conf.get('displayName', ''))
            if name:
                normalized = normalize_conference_name(name)
                return normalized, conf.get('id', '')

    # Strategy 4: Use team ID to get detailed info (extra API call; try to avoid)
    team_id = team_info.get('id')
    if team_id:
        conf_name, conf_id = get_team_details_from_api(team_id)
        if conf_name != 'Independent':
            normalized = normalize_conference_name(conf_name)
            return normalized, conf_id

    # Strategy 5: Heuristic mapping (legacy fallback)
    team_abbr = (team_info.get('abbreviation') or '').upper()
    team_name = team_info.get('displayName', '') or ''

    team_conference_map = {
        # SEC (including new additions)
        'ALA': 'SEC', 'UGA': 'SEC', 'LSU': 'SEC', 'FLA': 'SEC', 'TENN': 'SEC', 'AUB': 'SEC',
        'ARK': 'SEC', 'MISS': 'SEC', 'MSST': 'SEC', 'SC': 'SEC', 'UK': 'SEC', 'VU': 'SEC',
        'TAMU': 'SEC', 'MIZ': 'SEC', 'TEX': 'SEC', 'OU': 'SEC',

        # Big Ten (including West Coast additions)
        'OSU': 'Big Ten', 'MICH': 'Big Ten', 'PSU': 'Big Ten', 'WIS': 'Big Ten', 'IOWA': 'Big Ten',
        'MSU': 'Big Ten', 'NEB': 'Big Ten', 'MINN': 'Big Ten', 'ILL': 'Big Ten', 'IND': 'Big Ten',
        'PUR': 'Big Ten', 'NW': 'Big Ten', 'MD': 'Big Ten', 'RU': 'Big Ten', 'ORE': 'Big Ten',
        'WASH': 'Big Ten', 'UCLA': 'Big Ten', 'USC': 'Big Ten',

        # ACC (including additions)
        'CLEM': 'ACC', 'FSU': 'ACC', 'MIA': 'ACC', 'UNC': 'ACC', 'DUKE': 'ACC', 'NCSU': 'ACC',
        'VT': 'ACC', 'UVA': 'ACC', 'PITT': 'ACC', 'SYR': 'ACC', 'BC': 'ACC', 'LOU': 'ACC',
        'GT': 'ACC', 'WAKE': 'ACC', 'ND': 'Independent', 'CAL': 'ACC', 'STAN': 'ACC', 'SMU': 'ACC',

        # Big 12
        'BAY': 'Big 12', 'TCU': 'Big 12', 'OKST': 'Big 12', 'TTU': 'Big 12', 'KU': 'Big 12',
        'KSU': 'Big 12', 'ISU': 'Big 12', 'WVU': 'Big 12', 'CIN': 'Big 12', 'HOU': 'Big 12',
        'UCF': 'Big 12', 'BYU': 'Big 12', 'COLO': 'Big 12', 'UTAH': 'Big 12', 'ASU': 'Big 12',
        'ARIZ': 'Big 12',

        # Pac-12 (remaining)
        'ORST': 'Pac-12', 'WSU': 'Pac-12',

        # American Athletic Conference (post-realignment)
        'NAVY': 'American Athletic Conference', 'ARMY': 'American Athletic Conference',
        'TUL': 'American Athletic Conference', 'TLSA': 'American Athletic Conference',
        'MEM': 'American Athletic Conference', 'USF': 'American Athletic Conference',
        'ECU': 'American Athletic Conference', 'TEMP': 'American Athletic Conference',
        'UAB': 'American Athletic Conference', 'UTSA': 'American Athletic Conference',
        'FAU': 'American Athletic Conference', 'RICE': 'American Athletic Conference',
        'UNT': 'American Athletic Conference', 'CHAR': 'American Athletic Conference',

        # Mountain West
        'BSU': 'Mountain West', 'SDSU': 'Mountain West', 'FRES': 'Mountain West', 'CSU': 'Mountain West',
        'AFA': 'Mountain West', 'WYO': 'Mountain West', 'UNM': 'Mountain West', 'UNLV': 'Mountain West',
        'UNR': 'Mountain West', 'SJSU': 'Mountain West', 'USU': 'Mountain West', 'HAW': 'Mountain West',

        # MAC
        'BGSU': 'MAC', 'BUFF': 'MAC', 'CMU': 'MAC', 'EMU': 'MAC', 'KENT': 'MAC', 'M-OH': 'MAC',
        'NIU': 'MAC', 'OHIO': 'MAC', 'TOL': 'MAC', 'WMU': 'MAC', 'BALL': 'MAC', 'AKRON': 'MAC',

        # Conference USA
        'LT': 'Conference USA', 'WKU': 'Conference USA', 'MTSU': 'Conference USA', 'FIU': 'Conference USA',
        'JVST': 'Conference USA', 'UTEP': 'Conference USA', 'NMSU': 'Conference USA', 'SAM': 'Conference USA',
        'KENNT': 'Conference USA', 'LIBT': 'Conference USA',

        # Sun Belt
        'APP': 'Sun Belt', 'CCU': 'Sun Belt', 'GS': 'Sun Belt', 'GAST': 'Sun Belt', 'JMU': 'Sun Belt',
        'MRSH': 'Sun Belt', 'ODU': 'Sun Belt', 'STAL': 'Sun Belt', 'TROY': 'Sun Belt', 'ULM': 'Sun Belt',
        'ULL': 'Sun Belt', 'USA': 'Sun Belt', 'TXST': 'Sun Belt', 'ARKST': 'Sun Belt',

        # Independents
        'UMASS': 'Independent', 'UCONN': 'Independent'
    }

    if team_abbr in team_conference_map:
        return team_conference_map[team_abbr], ''

    if 'Texas A&M' in team_name or 'Texas A & M' in team_name:
        return 'SEC', ''
    elif 'Notre Dame' in team_name:
        return 'Independent', ''
    elif 'UMass' in team_name or 'Massachusetts' in team_name:
        return 'Independent', ''
    elif 'UConn' in team_name or 'Connecticut' in team_name:
        return 'Independent', ''

    return 'Independent', ''

def get_cfb_schedule_xml():
    """Get college football schedule and create schedule_cfb_2025.xml"""
    print("Fetching college football schedule...")

    # Try 2025 first, then 2024
    for year in [2025, 2024]:
        print(f"Trying {year}...")

        # Build the team_id -> conference map up front (authoritative)
        conf_index = build_conference_index(year)
        print(f"Conference index: {len(conf_index)} teams mapped")

        all_games = []

        # Get games week by week
        for week in range(1, 16):  # Weeks 1-15
            url = f"http://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?seasontype=2&week={week}&year={year}"

            try:
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                data = response.json()

                if 'events' in data and data['events']:
                    all_games.extend(data['events'])
                    print(f"Week {week}: {len(data['events'])} games")

                time.sleep(0.3)  # Be nice to ESPN

            except Exception:
                continue

        if all_games:
            print(f"✓ Found {len(all_games)} games for {year}")
            create_xml(all_games, year, conf_index)
            return
        else:
            print(f"✗ No games found for {year}")

    print("❌ Could not find any schedule data")

def create_xml(games, year, conf_index: dict):
    """Create XML file from games data, using standings-driven conference mapping"""

    # Create root element
    root = ET.Element("college_football_schedule")
    root.set("season", str(year))
    root.set("generated", datetime.now().isoformat())

    games_element = ET.SubElement(root, "games")

    valid_games = 0
    conference_stats = {}

    for game in games:
        try:
            # Get basic info
            game_id = game.get('id', '')
            game_date = game.get('date', '')

            # Format date
            if game_date:
                try:
                    dt = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%m/%d/%Y %I:%M %p')
                except Exception:
                    formatted_date = game_date
            else:
                formatted_date = 'TBD'

            # Get teams
            competitions = game.get('competitions', [])
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get('competitors', [])

            home_team_data = {}
            away_team_data = {}

            for competitor in competitors:
                team_info = competitor.get('team', {}) or {}
                team_id = str(team_info.get('id', '') or '')
                team_name = team_info.get('displayName', 'Unknown')
                team_abbreviation = team_info.get('abbreviation', '')
                team_location = team_info.get('location', '')
                team_nickname = team_info.get('name', '')
                team_color = team_info.get('color', '')
                team_alternate_color = team_info.get('alternateColor', '')
                # Logos may be under 'logo' or in 'logos' list with 'href'
                team_logo = team_info.get('logo', '')
                if not team_logo:
                    logos = team_info.get('logos') or []
                    if logos and isinstance(logos, list):
                        team_logo = logos[0].get('href', '') or ''

                # ---- Authoritative conference via standings map ----
                mapped_conf_raw = conf_index.get(team_id)
                if mapped_conf_raw:
                    conference_name, conference_id = normalize_conference_name(mapped_conf_raw), ''
                else:
                    # Fallback to older heuristics (less reliable)
                    conference_name, conference_id = get_conference_info_enhanced(team_info, competitor)
                    conference_name = normalize_conference_name(conference_name)
                # ----------------------------------------------------

                # Track conference stats
                conference_stats[conference_name] = conference_stats.get(conference_name, 0) + 1

                score = competitor.get('score', '')
                record = competitor.get('records', []) or []
                overall_record = ''
                for rec in record:
                    if rec.get('type') == 'total':
                        overall_record = rec.get('summary', '')
                        break

                team_data = {
                    'name': team_name,
                    'abbreviation': team_abbreviation,
                    'location': team_location,
                    'nickname': team_nickname,
                    'conference': conference_name,
                    'conference_id': conference_id,
                    'color': team_color,
                    'alternate_color': team_alternate_color,
                    'logo': team_logo,
                    'score': score,
                    'record': overall_record
                }

                if competitor.get('homeAway') == 'home':
                    home_team_data = team_data
                else:
                    away_team_data = team_data

            # Get venue and TV
            venue = competition.get('venue', {}) or {}
            stadium = venue.get('fullName', 'TBD')
            address = venue.get('address', {}) or {}
            stadium_city = address.get('city', '')
            stadium_state = address.get('state', '')

            broadcasts = competition.get('broadcasts', []) or []
            tv_channel = 'TBD'
            if broadcasts:
                media = broadcasts[0].get('media', {}) or {}
                tv_channel = media.get('shortName', 'TBD')

            # Game status
            status = competition.get('status', {}) or {}
            game_status = status.get('type', {}).get('description', 'Scheduled')

            # Week information
            week = competition.get('week', {}) or {}
            week_number = week.get('number', '')

            # Create XML game element
            game_element = ET.SubElement(games_element, "game")
            game_element.set("id", str(game_id))

            ET.SubElement(game_element, "date").text = formatted_date
            ET.SubElement(game_element, "status").text = game_status
            ET.SubElement(game_element, "week").text = str(week_number) if week_number else ""

            # Teams with enhanced info
            teams_element = ET.SubElement(game_element, "teams")

            # Away team
            away_elem = ET.SubElement(teams_element, "away_team")
            ET.SubElement(away_elem, "name").text = away_team_data.get('name', 'TBD')
            ET.SubElement(away_elem, "abbreviation").text = away_team_data.get('abbreviation', '')
            ET.SubElement(away_elem, "location").text = away_team_data.get('location', '')
            ET.SubElement(away_elem, "nickname").text = away_team_data.get('nickname', '')
            ET.SubElement(away_elem, "conference").text = away_team_data.get('conference', 'Independent')
            ET.SubElement(away_elem, "conference_id").text = away_team_data.get('conference_id', '')
            ET.SubElement(away_elem, "color").text = away_team_data.get('color', '')
            ET.SubElement(away_elem, "alternate_color").text = away_team_data.get('alternate_color', '')
            ET.SubElement(away_elem, "logo").text = away_team_data.get('logo', '')
            ET.SubElement(away_elem, "score").text = str(away_team_data.get('score', '')) if away_team_data.get('score') else ""
            ET.SubElement(away_elem, "record").text = away_team_data.get('record', '')

            # Home team
            home_elem = ET.SubElement(teams_element, "home_team")
            ET.SubElement(home_elem, "name").text = home_team_data.get('name', 'TBD')
            ET.SubElement(home_elem, "abbreviation").text = home_team_data.get('abbreviation', '')
            ET.SubElement(home_elem, "location").text = home_team_data.get('location', '')
            ET.SubElement(home_elem, "nickname").text = home_team_data.get('nickname', '')
            ET.SubElement(home_elem, "conference").text = home_team_data.get('conference', 'Independent')
            ET.SubElement(home_elem, "conference_id").text = home_team_data.get('conference_id', '')
            ET.SubElement(home_elem, "color").text = home_team_data.get('color', '')
            ET.SubElement(home_elem, "alternate_color").text = home_team_data.get('alternate_color', '')
            ET.SubElement(home_elem, "logo").text = home_team_data.get('logo', '')
            ET.SubElement(home_elem, "score").text = str(home_team_data.get('score', '')) if home_team_data.get('score') else ""
            ET.SubElement(home_elem, "record").text = home_team_data.get('record', '')

            # Venue and broadcast
            venue_elem = ET.SubElement(game_element, "venue")
            ET.SubElement(venue_elem, "stadium").text = stadium
            ET.SubElement(venue_elem, "city").text = stadium_city
            ET.SubElement(venue_elem, "state").text = stadium_state

            broadcast_elem = ET.SubElement(game_element, "broadcast")
            ET.SubElement(broadcast_elem, "tv_channel").text = tv_channel

            valid_games += 1

        except Exception as e:
            print(f"Error processing game: {e}")
            continue

    # Print conference statistics
    print("\n=== CONFERENCE DISTRIBUTION ===")
    for conf, count in sorted(conference_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"{conf}: {count} teams")

    # Add summary
    summary = ET.SubElement(root, "summary")
    ET.SubElement(summary, "total_games").text = str(valid_games)
    ET.SubElement(summary, "last_updated").text = datetime.now().isoformat()

    # Add conference statistics to XML
    conferences_elem = ET.SubElement(summary, "conferences")
    for conf, count in conference_stats.items():
        conf_elem = ET.SubElement(conferences_elem, "conference")
        conf_elem.set("name", conf)
        conf_elem.set("teams", str(count))

    # Pretty print and save
    rough_string = ET.tostring(root, 'unicode')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])

    filename = "cfb_schedule.xml"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)

    print(f"✅ Created {filename} with {valid_games} games")

if __name__ == "__main__":
    # Uncomment to debug API structure first
    # debug_api_structure()

    get_cfb_schedule_xml()
