#!/usr/bin/env python3
"""
ESPN NFL 2025 Schedule Scraper and XML Converter
Fetches the complete 2025 NFL regular season schedule from ESPN's API
and saves it as an XML file.
"""

import requests
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys
from datetime import datetime
import time
import os
from urllib.parse import urlparse

class NFLScheduleScraper:
    def __init__(self):
        self.base_url = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
        self.site_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.espn.com/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        self.schedule_data = []
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def debug_response(self, response, description="Response"):
        """Debug helper to inspect API responses"""
        print(f"\n{description}:")
        print(f"Status Code: {response.status_code}")
        print(f"URL: {response.url}")
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, list):
                            print(f"  {key}: list with {len(value)} items")
                            if value and len(value) > 0:
                                print(f"    First item type: {type(value[0])}")
                                if isinstance(value[0], dict):
                                    print(f"    First item keys: {list(value[0].keys())}")
                        elif isinstance(value, dict):
                            print(f"  {key}: dict with keys {list(value.keys())}")
                        else:
                            print(f"  {key}: {type(value)} = {str(value)[:100]}")
            except Exception as e:
                print(f"Error parsing JSON: {e}")
                print(f"Raw content (first 500 chars): {response.text[:500]}")

    def fetch_event_from_url(self, event_url):
        """Fetch event data from a reference URL"""
        try:
            print(f"Fetching event details from: {event_url}")
            response = self.session.get(event_url, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching event from URL {event_url}: {e}")
            return None

    def fetch_scoreboard_current(self):
        """Fetch current scoreboard to see data structure"""
        url = f"{self.site_url}/scoreboard"
        print(f"Fetching current scoreboard: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.debug_response(response, "Current Scoreboard")
            data = response.json()
            
            if 'events' in data and data['events']:
                print(f"Found {len(data['events'])} current events")
                # Use first event as template to understand structure
                first_event = data['events'][0]
                print(f"Sample event structure: {json.dumps(first_event, indent=2)[:1000]}...")
                return data['events']
            return []
            
        except Exception as e:
            print(f"Error fetching current scoreboard: {e}")
            return []

    def fetch_all_events_detailed(self):
        """Fetch all regular season events and resolve references"""
        url = f"{self.base_url}/seasons/2025/types/2/events?limit=1000"
        print(f"Fetching all events from: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.debug_response(response, "All Events API")
            data = response.json()
            
            if 'items' not in data:
                print("No 'items' key found in response")
                return []
            
            events = data['items']
            print(f"Found {len(events)} event references")
            
            # Check if these are $ref objects
            if events and isinstance(events[0], dict) and '$ref' in events[0]:
                print("Events are in $ref format - will resolve during processing")
                return events  # Return the $ref objects, resolve them in process_event_data
            
            detailed_events = []
            for i, event in enumerate(events[:50]):  # Process up to 50 events
                print(f"Processing event {i+1}/{min(len(events), 50)}")
                
                if isinstance(event, str) and event.startswith('http'):
                    # This is a reference URL
                    event_data = self.fetch_event_from_url(event)
                    if event_data:
                        detailed_events.append(event_data)
                elif isinstance(event, dict):
                    # This is actual event data
                    detailed_events.append(event)
                
                # Rate limiting
                time.sleep(0.2)
            
            return detailed_events
            
        except Exception as e:
            print(f"Error fetching all events: {e}")
            return []

    def fetch_week_by_week_detailed(self):
        """Fetch schedule week by week for 2025 regular season"""
        all_games = []
        
        print("Fetching schedule week by week...")
        
        # Try different date formats and parameters
        date_formats = [
            "2025",
            "20250901-20260201",  # Sept 2025 to Feb 2026
            None  # No date parameter
        ]
        
        for date_param in date_formats:
            print(f"\nTrying date format: {date_param}")
            
            for week in range(1, 4):  # Test first 3 weeks
                if date_param:
                    url = f"{self.site_url}/scoreboard?seasontype=2&week={week}&dates={date_param}"
                else:
                    url = f"{self.site_url}/scoreboard?seasontype=2&week={week}"
                
                print(f"Fetching Week {week}: {url}")
                
                try:
                    response = self.session.get(url, timeout=15)
                    response.raise_for_status()
                    
                    if week == 1:  # Debug first week
                        self.debug_response(response, f"Week {week} with date {date_param}")
                    
                    data = response.json()
                    
                    if 'events' in data and data['events']:
                        for event in data['events']:
                            if event not in all_games:  # Avoid duplicates
                                all_games.append(event)
                        print(f"  Week {week}: {len(data['events'])} games (total: {len(all_games)})")
                        
                        # If we found games with this date format, continue with it
                        if data['events']:
                            break
                    else:
                        print(f"  Week {week}: No games found")
                        
                    time.sleep(0.3)
                    
                except Exception as e:
                    print(f"Error fetching week {week}: {e}")
                    continue
            
            # If we found games, stop trying other date formats
            if all_games:
                print(f"Success with date format: {date_param}")
                break
        
        print(f"Total games fetched: {len(all_games)}")
        return all_games

    def fetch_by_date_range(self):
        """Try fetching by specific date ranges"""
        print("Trying date range approach...")
        
        # NFL season typically runs Sept-Jan
        date_ranges = [
            "20250904-20250910",  # Week 1 (Sept 4-10, 2025)
            "20250911-20250917",  # Week 2
            "20250918-20250924",  # Week 3
        ]
        
        all_games = []
        
        for date_range in date_ranges:
            url = f"{self.site_url}/scoreboard?dates={date_range}"
            print(f"Fetching {date_range}: {url}")
            
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                if 'events' in data and data['events']:
                    all_games.extend(data['events'])
                    print(f"  {date_range}: {len(data['events'])} games")
                else:
                    print(f"  {date_range}: No games")
                
                time.sleep(0.3)
                
            except Exception as e:
                print(f"Error fetching {date_range}: {e}")
        
        return all_games

    def try_alternative_endpoints(self):
        """Try alternative ESPN endpoints"""
        print("Trying alternative endpoints...")
        
        endpoints = [
            f"{self.site_url}/scoreboard?seasontype=2",
            f"{self.site_url}/schedule",
            f"{self.base_url}/seasons/2025/types/2/weeks",
            f"{self.base_url}/calendar",
        ]
        
        for endpoint in endpoints:
            print(f"\nTrying endpoint: {endpoint}")
            try:
                response = self.session.get(endpoint, timeout=15)
                response.raise_for_status()
                self.debug_response(response, f"Alternative endpoint")
                data = response.json()
                
                # Look for any events or schedule data
                if isinstance(data, dict):
                    if 'events' in data and data['events']:
                        print(f"Found events in this endpoint!")
                        return data['events']
                    elif 'items' in data and data['items']:
                        print(f"Found items in this endpoint!")
                        return data['items']
                
            except Exception as e:
                print(f"Error with endpoint {endpoint}: {e}")
        
        return []

    def process_event_data(self, events):
        """Process and clean the event data"""
        processed_games = []
        
        print(f"Processing {len(events)} events...")
        
        for i, event in enumerate(events):
            try:
                print(f"Processing event {i+1}: {type(event)}")
                
                # Handle ESPN's $ref pattern
                if isinstance(event, dict) and '$ref' in event:
                    ref_url = event['$ref']
                    print(f"  Fetching from $ref URL: {ref_url}")
                    event_data = self.fetch_event_from_url(ref_url)
                    if not event_data:
                        print(f"  Failed to fetch from $ref URL")
                        continue
                    event = event_data
                
                # Handle string references
                elif isinstance(event, str):
                    if event.startswith('http'):
                        print(f"  Fetching from URL: {event[:80]}...")
                        event_data = self.fetch_event_from_url(event)
                        if not event_data:
                            continue
                        event = event_data
                    else:
                        print(f"  Skipping string: {event[:50]}...")
                        continue
                
                # Now process the actual event data
                if not isinstance(event, dict):
                    print(f"  Unexpected event type: {type(event)}")
                    continue
                
                # Debug first few events
                if i < 3:
                    print(f"  Event keys: {list(event.keys())}")
                    if 'week' in event:
                        print(f"  Week data: {event['week']}")
                    if 'competitions' in event and event['competitions']:
                        comp = event['competitions'][0]
                        if 'week' in comp:
                            print(f"  Competition week: {comp['week']}")
                
                # Extract week number with multiple fallback strategies
                week_number = ''
                
                print(f"  DEBUG: Starting week extraction for event {event.get('id', 'no-id')}")
                print(f"  DEBUG: Event date: {event.get('date', 'NO DATE FOUND')}")
                
                # Strategy 1: Direct week.number
                week_number = self.get_nested_value(event, ['week', 'number'], '')
                if week_number:
                    week_number = str(week_number)
                    print(f"  DEBUG: Found week in event.week.number: {week_number}")
                else:
                    print(f"  DEBUG: No week found in event.week.number")
                
                # Strategy 2: Try competition week data
                if not week_number:
                    week_number = self.get_week_from_competition_data(event)
                    if week_number:
                        print(f"  DEBUG: Found week in competition data: {week_number}")
                    else:
                        print(f"  DEBUG: No week found in competition data")
                
                # Strategy 3: Try season week
                if not week_number:
                    week_number = self.get_nested_value(event, ['season', 'week', 'number'], '')
                    if week_number:
                        week_number = str(week_number)
                        print(f"  DEBUG: Found week in season data: {week_number}")
                    else:
                        print(f"  DEBUG: No week found in season data")
                
                # Strategy 4: FORCE date estimation for all games with dates
                if not week_number:
                    event_date = event.get('date')
                    if event_date:
                        print(f"  DEBUG: Attempting date estimation with date: {event_date}")
                        week_number = self.estimate_week_from_date(event_date)
                        if week_number:
                            print(f"  DEBUG: Successfully estimated week from date: {week_number}")
                        else:
                            print(f"  DEBUG: Date estimation failed!")
                    else:
                        print(f"  DEBUG: No date available for estimation")
                
                # Final check
                if not week_number:
                    print(f"  ERROR: Could not determine week for game {event.get('name', 'unknown')}")
                    # Set a default based on date if we have one
                    if event.get('date'):
                        print(f"  DEBUG: Making one final attempt at date parsing...")
                        try:
                            from datetime import datetime
                            date_str = event['date']
                            if 'T' in date_str:
                                if date_str.endswith('Z'):
                                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                else:
                                    game_date = datetime.fromisoformat(date_str)
                                
                                # Simple month-based estimation for 2025 NFL season
                                month = game_date.month
                                day = game_date.day
                                
                                if month == 9:  # September
                                    if day <= 10:
                                        week_number = '1'
                                    elif day <= 17:
                                        week_number = '2'
                                    elif day <= 24:
                                        week_number = '3'
                                    else:
                                        week_number = '4'
                                elif month == 10:  # October
                                    week_number = str(4 + ((day - 1) // 7) + 1)
                                elif month == 11:  # November
                                    week_number = str(8 + ((day - 1) // 7) + 1)
                                elif month == 12:  # December
                                    week_number = str(12 + ((day - 1) // 7) + 1)
                                elif month == 1 and game_date.year == 2026:  # January Week 18
                                    week_number = '18'
                                
                                if week_number:
                                    print(f"  DEBUG: Manual date parsing succeeded: {week_number}")
                                
                        except Exception as e:
                            print(f"  DEBUG: Manual date parsing failed: {e}")
                
                print(f"  FINAL: Week determined as: '{week_number}'")
                
                game = {
                    'id': event.get('id', ''),
                    'name': event.get('name', ''),
                    'short_name': event.get('shortName', ''),
                    'date': event.get('date', ''),
                    'status': self.get_nested_value(event, ['status', 'type', 'name'], ''),
                    'week': week_number,
                    'season': self.get_nested_value(event, ['season', 'year'], 2025),
                    'venue': '',
                    'city': '',
                    'state': '',
                    'teams': []
                }
                
                # Extract competition details
                competitions = event.get('competitions', [])
                if competitions and len(competitions) > 0:
                    comp = competitions[0]
                    
                    # Venue information
                    venue = comp.get('venue', {})
                    if venue and not isinstance(venue, str):
                        game['venue'] = venue.get('fullName', '')
                        address = venue.get('address', {})
                        if address and not isinstance(address, str):
                            game['city'] = address.get('city', '')
                            game['state'] = address.get('state', '')
                    
                    # Team information - resolve $ref if needed
                    competitors = comp.get('competitors', [])
                    for competitor in competitors:
                        # Handle $ref in competitor
                        if isinstance(competitor, dict) and '$ref' in competitor:
                            competitor_url = competitor['$ref']
                            print(f"    Fetching competitor from: {competitor_url}")
                            competitor_data = self.fetch_event_from_url(competitor_url)
                            if competitor_data:
                                competitor = competitor_data
                            else:
                                continue
                        
                        # Extract team data
                        team_data = competitor.get('team', {})
                        
                        # Handle $ref in team data
                        if isinstance(team_data, dict) and '$ref' in team_data:
                            team_url = team_data['$ref']
                            print(f"    Fetching team from: {team_url}")
                            team_full_data = self.fetch_event_from_url(team_url)
                            if team_full_data:
                                team_data = team_full_data
                        
                        # Build team object with safe extraction
                        team = {
                            'id': self.safe_extract(competitor, 'id'),
                            'name': self.safe_extract(team_data, 'displayName') or self.safe_extract(team_data, 'name'),
                            'abbreviation': self.safe_extract(team_data, 'abbreviation'),
                            'location': self.safe_extract(team_data, 'location'),
                            'home_away': self.safe_extract(competitor, 'homeAway'),
                            'score': self.safe_extract(competitor, 'score', '0'),
                            'record': ''
                        }
                        
                        # Get team record - handle $ref
                        records = competitor.get('records', [])
                        if records and len(records) > 0:
                            record = records[0]
                            if isinstance(record, dict) and '$ref' in record:
                                record_url = record['$ref']
                                record_data = self.fetch_event_from_url(record_url)
                                if record_data:
                                    team['record'] = record_data.get('summary', '')
                            else:
                                team['record'] = record.get('summary', '')
                        
                        # Handle score $ref
                        score = competitor.get('score')
                        if isinstance(score, dict) and '$ref' in score:
                            score_url = score['$ref']
                            print(f"    Fetching score from: {score_url}")
                            score_data = self.fetch_event_from_url(score_url)
                            if score_data and 'value' in score_data:
                                team['score'] = str(score_data['value'])
                        
                        game['teams'].append(team)
                
                # Only add games with some actual data
                if game['id'] or game['name'] or (game['teams'] and any(t['name'] for t in game['teams'])):
                    processed_games.append(game)
                    if i < 3:
                        team_names = [t['name'] for t in game['teams'] if t['name']]
                        print(f"  Successfully processed: {game['name'] or ' vs '.join(team_names)} ({game['id']})")
                else:
                    print(f"  Skipping empty game data")
                
            except Exception as e:
                print(f"Error processing event {i}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"Successfully processed {len(processed_games)} games")
        return processed_games

    def estimate_week_from_date(self, date_str):
        """Estimate NFL week from game date"""
        try:
            from datetime import datetime
            
            # Handle different date formats
            if date_str.endswith('Z'):
                game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                game_date = datetime.fromisoformat(date_str)
            
            # NFL 2025 season starts September 4, 2025 (Thursday Night Football)
            # Week 1 runs Sept 4-10, Week 2 runs Sept 11-17, etc.
            season_start = datetime(2025, 9, 4)
            
            if game_date < season_start:
                return ''  # Preseason
            
            # Calculate week number
            days_since_start = (game_date - season_start).days
            week_number = (days_since_start // 7) + 1
            
            # Regular season is weeks 1-18 (17 games over 18 weeks)
            if 1 <= week_number <= 18:
                print(f"    Estimated week {week_number} from date {date_str}")
                return str(week_number)
            elif week_number > 18:
                # Handle games beyond Week 18 - but for 2025 regular season, 
                # games in January 2026 should be Week 18 (final regular season week)
                if game_date.month == 1 and game_date.year == 2026:
                    print(f"    January game mapped to Week 18 from date {date_str}")
                    return '18'  # Week 18 is the final regular season week
                else:
                    # True playoffs would start later
                    playoff_week = week_number - 18
                    print(f"    Estimated playoff week {playoff_week} from date {date_str}")
                    return f"P{playoff_week}"  # P1, P2, P3, etc.
            
            return ''
            
        except Exception as e:
            print(f"    Error estimating week from date {date_str}: {e}")
            return ''

    def get_week_from_competition_data(self, event):
        """Try to extract week from various competition data sources"""
        try:
            competitions = event.get('competitions', [])
            if not competitions:
                return ''
                
            comp = competitions[0]
            
            # Check if competition has week data
            if 'week' in comp:
                week_data = comp['week']
                if isinstance(week_data, dict):
                    return str(week_data.get('number', ''))
                elif isinstance(week_data, (int, str)):
                    return str(week_data)
            
            # Check season type and week in competition
            season_type = comp.get('seasonType', {})
            if isinstance(season_type, dict) and 'week' in season_type:
                return str(season_type['week'])
                
            return ''
            
        except Exception as e:
            print(f"    Error extracting week from competition: {e}")
            return ''

    def safe_extract(self, data, key, default=''):
        """Safely extract value from data, handling $ref objects"""
        if not isinstance(data, dict):
            return default
        
        value = data.get(key, default)
        
        # If it's a $ref, we should have resolved it already, but handle gracefully
        if isinstance(value, dict) and '$ref' in value:
            print(f"    Warning: Unresolved $ref in {key}: {value['$ref']}")
            return default
        
        return value if value is not None else default

    def get_nested_value(self, data, keys, default=None):
        """Safely get nested dictionary values"""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default

    def convert_to_xml(self, games):
        """Convert games data to XML format"""
        root = ET.Element("nfl_schedule_2025")
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "season").text = "2025"
        ET.SubElement(metadata, "season_type").text = "Regular Season"
        ET.SubElement(metadata, "total_games").text = str(len(games))
        ET.SubElement(metadata, "generated_date").text = datetime.now().isoformat()
        
        # Add games
        games_element = ET.SubElement(root, "games")
        
        for game in games:
            game_element = ET.SubElement(games_element, "game")
            
            ET.SubElement(game_element, "id").text = str(game.get('id', ''))
            ET.SubElement(game_element, "name").text = game.get('name', '')
            ET.SubElement(game_element, "short_name").text = game.get('short_name', '')
            ET.SubElement(game_element, "date").text = game.get('date', '')
            ET.SubElement(game_element, "status").text = game.get('status', '')
            ET.SubElement(game_element, "week").text = str(game.get('week', ''))
            ET.SubElement(game_element, "season").text = str(game.get('season', 2025))
            
            # Competition details
            competition = ET.SubElement(game_element, "competition")
            ET.SubElement(competition, "venue").text = game.get('venue', '')
            ET.SubElement(competition, "city").text = game.get('city', '')
            ET.SubElement(competition, "state").text = game.get('state', '')
            
            # Teams
            teams_element = ET.SubElement(competition, "teams")
            for team in game.get('teams', []):
                team_element = ET.SubElement(teams_element, "team")
                ET.SubElement(team_element, "id").text = str(team.get('id', ''))
                ET.SubElement(team_element, "name").text = team.get('name', '')
                ET.SubElement(team_element, "abbreviation").text = team.get('abbreviation', '')
                ET.SubElement(team_element, "location").text = team.get('location', '')
                ET.SubElement(team_element, "home_away").text = team.get('home_away', '')
                ET.SubElement(team_element, "score").text = str(team.get('score', '0'))
                ET.SubElement(team_element, "record").text = team.get('record', '')
        
        return root

    def prettify_xml(self, elem):
        """Return a pretty-printed XML string"""
        rough_string = ET.tostring(elem, 'unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    def get_script_directory(self):
        """Get the directory where this script is located"""
        return os.path.dirname(os.path.abspath(__file__))

    def load_existing_data(self, filepath):
        """Load existing JSON data if file exists"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('games', [])
            except Exception as e:
                print(f"Warning: Could not load existing data from {filepath}: {e}")
        return []

    def merge_game_data(self, existing_games, new_games):
        """Merge new games with existing, update changed data, preserve existing"""
        # Create lookup dictionaries
        existing_by_id = {game['id']: game for game in existing_games if game.get('id')}
        new_by_id = {game['id']: game for game in new_games if game.get('id')}
        
        merged_games = []
        updated_count = 0
        new_count = 0
        
        # Process existing games - update if we have new data
        for game_id, existing_game in existing_by_id.items():
            if game_id in new_by_id:
                new_game = new_by_id[game_id]
                if self.games_differ(existing_game, new_game):
                    # Update with new data but preserve any additional fields
                    updated_game = self.merge_single_game(existing_game, new_game)
                    merged_games.append(updated_game)
                    updated_count += 1
                    print(f"  Updated: {updated_game.get('name', game_id)}")
                else:
                    # No changes, keep existing
                    merged_games.append(existing_game)
            else:
                # Keep existing game (not in new data)
                merged_games.append(existing_game)
        
        # Add completely new games
        for game_id, new_game in new_by_id.items():
            if game_id not in existing_by_id:
                merged_games.append(new_game)
                new_count += 1
                print(f"  Added: {new_game.get('name', game_id)}")
        
        print(f"📊 Merge summary: {len(merged_games)} total games, {updated_count} updated, {new_count} new")
        return merged_games

    def games_differ(self, game1, game2):
        """Check if two games have different data"""
        # Compare key fields that might change
        key_fields = ['name', 'short_name', 'date', 'status', 'week', 'venue', 'city', 'state']
        
        for field in key_fields:
            if game1.get(field) != game2.get(field):
                return True
        
        # Compare teams data
        teams1 = game1.get('teams', [])
        teams2 = game2.get('teams', [])
        
        if len(teams1) != len(teams2):
            return True
        
        for i, team1 in enumerate(teams1):
            if i < len(teams2):
                team2 = teams2[i]
                team_fields = ['name', 'abbreviation', 'score', 'record']
                for field in team_fields:
                    if team1.get(field) != team2.get(field):
                        return True
        
        return False

    def merge_single_game(self, existing_game, new_game):
        """Merge data from a single game, preferring new data but preserving existing fields"""
        merged = existing_game.copy()
        
        # Update with new data
        for key, value in new_game.items():
            if value:  # Only update if new value is not empty
                merged[key] = value
        
        # Special handling for teams - merge team data
        if 'teams' in new_game and new_game['teams']:
            existing_teams = {team.get('id'): team for team in existing_game.get('teams', [])}
            merged_teams = []
            
            for new_team in new_game['teams']:
                team_id = new_team.get('id')
                if team_id in existing_teams:
                    # Merge team data
                    merged_team = existing_teams[team_id].copy()
                    for key, value in new_team.items():
                        if value:
                            merged_team[key] = value
                    merged_teams.append(merged_team)
                else:
                    merged_teams.append(new_team)
            
            merged['teams'] = merged_teams
        
        # Update last_updated timestamp
        merged['last_updated'] = datetime.now().isoformat()
        
        return merged

    def save_json(self, data, filename=None):
        """Save JSON data with merge capability"""
        script_dir = self.get_script_directory()
        
        if not filename:
            filename = "2025_nfl_schedule.json"
        
        filename = os.path.basename(filename)
        full_path = os.path.join(script_dir, filename)
        
        # Load existing data and merge
        existing_games = self.load_existing_data(full_path)
        new_games = data.get('games', [])
        
        if existing_games:
            print(f"📋 Found existing file with {len(existing_games)} games")
            print("🔄 Merging with new data...")
            merged_games = self.merge_game_data(existing_games, new_games)
        else:
            print("📄 Creating new file")
            merged_games = new_games
        
        # Update metadata
        final_data = data.copy()
        final_data['games'] = merged_games
        final_data['metadata']['total_games'] = len(merged_games)
        final_data['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Create backup of existing file if it exists
        if os.path.exists(full_path):
            backup_path = full_path.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            try:
                import shutil
                shutil.copy2(full_path, backup_path)
                print(f"📦 Backup created: {os.path.basename(backup_path)}")
            except Exception as e:
                print(f"Warning: Could not create backup: {e}")
        
        # Save merged data
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        
        print(f"JSON file saved as: {full_path}")
        return full_path

    def save_xml(self, xml_root, filename=None, games_data=None):
        """Save XML to file with merge capability"""
        script_dir = self.get_script_directory()
        
        if not filename:
            filename = "2025_nfl_schedule.xml"
        
        filename = os.path.basename(filename)
        full_path = os.path.join(script_dir, filename)
        
        # Create backup of existing file if it exists
        if os.path.exists(full_path):
            backup_path = full_path.replace('.xml', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml')
            try:
                import shutil
                shutil.copy2(full_path, backup_path)
                print(f"📦 XML backup created: {os.path.basename(backup_path)}")
            except Exception as e:
                print(f"Warning: Could not create XML backup: {e}")
        
        xml_string = self.prettify_xml(xml_root)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        
        print(f"XML file saved as: {full_path}")
        return full_path

    def run(self, method='all'):
        """Main execution method"""
        print("=" * 60)
        print("ESPN NFL 2025 Schedule Scraper (Enhanced Debug Version)")
        print("=" * 60)
        
        events = []
        
        # First, try to understand current data structure
        print("\n🔍 Testing current scoreboard structure...")
        current_events = self.fetch_scoreboard_current()
        
        # Try different fetch methods
        if method == 'all' or method == 'events':
            print("\n1. Trying to fetch all events with detailed resolution...")
            events = self.fetch_all_events_detailed()
        
        if not events and (method == 'all' or method == 'weeks'):
            print("\n2. Trying week-by-week fetch with multiple formats...")
            events = self.fetch_week_by_week_detailed()
        
        if not events and (method == 'all' or method == 'dates'):
            print("\n3. Trying date range approach...")
            events = self.fetch_by_date_range()
        
        if not events and (method == 'all' or method == 'alternative'):
            print("\n4. Trying alternative endpoints...")
            events = self.try_alternative_endpoints()
        
        if not events:
            print("\n❌ No data could be fetched with any method.")
            print("This might be due to:")
            print("- ESPN API access restrictions")
            print("- 2025 schedule not yet available in the API")
            print("- API endpoint changes")
            print("- Network/firewall issues")
            return False
        
        print(f"\n✅ Successfully fetched {len(events)} raw events")
        
        # Process the data
        print("\nProcessing event data...")
        processed_games = self.process_event_data(events)
        
        if not processed_games:
            print("❌ No games could be processed from the fetched data.")
            print("This suggests the data structure might be different than expected.")
            
            # Save raw data for analysis
            print("Saving raw data for analysis...")
            script_dir = self.get_script_directory()
            raw_filename = "2025_nfl_schedule_raw_debug.json"
            raw_full_path = os.path.join(script_dir, raw_filename)
            with open(raw_full_path, 'w') as f:
                json.dump(events, f, indent=2)
            print(f"Raw data saved to: {raw_full_path}")
            
            return False
        
        print(f"✅ Processed {len(processed_games)} games")
        
        # Save JSON backup
        print("\nSaving JSON backup...")
        json_file = self.save_json({
            'metadata': {
                'season': 2025,
                'season_type': 'Regular Season',
                'total_games': len(processed_games),
                'generated_date': datetime.now().isoformat()
            },
            'games': processed_games
        })
        
        # Convert to XML (use merged data for XML too)
        print("\nConverting to XML...")
        xml_root = self.convert_to_xml(processed_games)
        
        # Save XML file
        print("\nSaving XML file...")
        xml_file = self.save_xml(xml_root, games_data=processed_games)
        
        print(f"\n🎉 Success! Files created:")
        print(f"📄 XML: {xml_file}")
        print(f"📄 JSON: {json_file}")
        
        return True

def main():
    """Main function"""
    scraper = NFLScheduleScraper()
    
    # Check command line arguments
    method = 'all'
    if len(sys.argv) > 1:
        method = sys.argv[1].lower()
        if method not in ['all', 'events', 'weeks', 'dates', 'alternative']:
            print("Usage: python scrape_nfl.py [all|events|weeks|dates|alternative]")
            print("  all         - Try all methods (default)")
            print("  events      - Fetch all events at once")
            print("  weeks       - Fetch week by week")
            print("  dates       - Fetch by date ranges")
            print("  alternative - Try alternative endpoints")
            sys.exit(1)
    
    try:
        success = scraper.run(method)
        if success:
            print("\n✅ Script completed successfully!")
        else:
            print("\n❌ Script failed to complete.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Script interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()