#!/usr/bin/env python3
"""
ESPN NFL Teams Scraper 2025
Fetches all 32 NFL teams data from ESPN's API and saves as XML
"""

import requests
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys
from datetime import datetime
import time
import os

class NFLTeamsScraper:
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
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_script_directory(self):
        """Get the directory where this script is located"""
        return os.path.dirname(os.path.abspath(__file__))

    def fetch_teams_list(self):
        """Fetch list of all NFL teams"""
        url = f"{self.site_url}/teams"
        print(f"Fetching teams list from: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'sports' in data and data['sports']:
                sport = data['sports'][0]
                if 'leagues' in sport and sport['leagues']:
                    league = sport['leagues'][0]
                    if 'teams' in league:
                        teams = league['teams']
                        print(f"Found {len(teams)} teams")
                        return teams
            
            # Fallback - try direct teams endpoint
            print("Trying alternative teams endpoint...")
            return self.fetch_teams_alternative()
            
        except Exception as e:
            print(f"Error fetching teams list: {e}")
            return self.fetch_teams_alternative()

    def fetch_teams_alternative(self):
        """Alternative method to fetch teams"""
        url = f"{self.base_url}/teams?limit=50"
        print(f"Fetching teams from: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'items' in data:
                print(f"Found {len(data['items'])} team references")
                return data['items']
            
            return []
            
        except Exception as e:
            print(f"Error with alternative teams fetch: {e}")
            return []

    def fetch_team_details(self, team_ref):
        """Fetch detailed team information from reference"""
        try:
            if isinstance(team_ref, dict) and '$ref' in team_ref:
                team_url = team_ref['$ref']
            elif isinstance(team_ref, str) and team_ref.startswith('http'):
                team_url = team_ref
            elif isinstance(team_ref, dict) and 'team' in team_ref:
                # This is already detailed team data
                return team_ref['team']
            else:
                print(f"Unknown team reference format: {type(team_ref)}")
                return None
            
            print(f"  Fetching team details from: {team_url}")
            response = self.session.get(team_url, timeout=15)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"  Error fetching team details: {e}")
            return None

    def process_team_data(self, teams_data):
        """Process team data and extract relevant information"""
        processed_teams = []
        
        print(f"Processing {len(teams_data)} teams...")
        
        for i, team_ref in enumerate(teams_data):
            try:
                print(f"Processing team {i+1}/{len(teams_data)}")
                
                # Fetch detailed team data
                team_data = self.fetch_team_details(team_ref)
                if not team_data:
                    continue
                
                # Handle direct team data vs reference
                if isinstance(team_data, dict) and 'team' in team_data:
                    team = team_data['team']
                else:
                    team = team_data
                
                # Extract team information
                team_info = {
                    'id': team.get('id', ''),
                    'guid': team.get('guid', ''),
                    'uid': team.get('uid', ''),
                    'name': team.get('name', ''),
                    'display_name': team.get('displayName', ''),
                    'short_display_name': team.get('shortDisplayName', ''),
                    'nickname': team.get('nickname', ''),
                    'location': team.get('location', ''),
                    'abbreviation': team.get('abbreviation', ''),
                    'color': team.get('color', ''),
                    'alternate_color': team.get('alternateColor', ''),
                    'is_active': team.get('isActive', True),
                    'is_all_star': team.get('isAllStar', False),
                    'logos': [],
                    'record': {},
                    'venue': {},
                    'conference': '',
                    'division': ''
                }
                
                # Extract logos
                if 'logos' in team and team['logos']:
                    for logo in team['logos']:
                        logo_info = {
                            'href': logo.get('href', ''),
                            'alt': logo.get('alt', ''),
                            'rel': logo.get('rel', []),
                            'width': logo.get('width', ''),
                            'height': logo.get('height', '')
                        }
                        team_info['logos'].append(logo_info)
                
                # Extract venue information
                if 'venue' in team and team['venue']:
                    venue = team['venue']
                    # Handle venue reference
                    if isinstance(venue, dict) and '$ref' in venue:
                        venue_data = self.fetch_venue_details(venue['$ref'])
                        if venue_data:
                            venue = venue_data
                    
                    if isinstance(venue, dict):
                        team_info['venue'] = {
                            'id': venue.get('id', ''),
                            'name': venue.get('fullName', ''),
                            'capacity': venue.get('capacity', ''),
                            'grass': venue.get('grass', ''),
                            'city': '',
                            'state': ''
                        }
                        
                        # Extract address
                        if 'address' in venue and venue['address']:
                            address = venue['address']
                            team_info['venue']['city'] = address.get('city', '')
                            team_info['venue']['state'] = address.get('state', '')
                
                # Extract group information (conference/division)
                if 'groups' in team and team['groups']:
                    for group in team['groups']:
                        if isinstance(group, dict) and '$ref' in group:
                            group_data = self.fetch_group_details(group['$ref'])
                            if group_data:
                                group = group_data
                        
                        if isinstance(group, dict):
                            group_name = group.get('name', '').lower()
                            if 'conference' in group_name:
                                team_info['conference'] = group.get('name', '')
                            elif 'division' in group_name or any(div in group_name for div in ['east', 'west', 'north', 'south']):
                                team_info['division'] = group.get('name', '')
                
                # Extract current record
                if 'record' in team and team['record']:
                    record = team['record']
                    if isinstance(record, dict) and '$ref' in record:
                        record_data = self.fetch_record_details(record['$ref'])
                        if record_data:
                            record = record_data
                    
                    if isinstance(record, dict):
                        team_info['record'] = {
                            'wins': record.get('wins', 0),
                            'losses': record.get('losses', 0),
                            'ties': record.get('ties', 0),
                            'percentage': record.get('percentage', 0.0),
                            'summary': record.get('summary', '')
                        }
                
                processed_teams.append(team_info)
                print(f"  Successfully processed: {team_info['display_name']} ({team_info['abbreviation']})")
                
                # Rate limiting
                time.sleep(0.3)
                
            except Exception as e:
                print(f"Error processing team {i+1}: {e}")
                continue
        
        print(f"Successfully processed {len(processed_teams)} teams")
        return processed_teams

    def fetch_venue_details(self, venue_url):
        """Fetch venue details from reference URL"""
        try:
            response = self.session.get(venue_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"    Error fetching venue: {e}")
            return None

    def fetch_group_details(self, group_url):
        """Fetch group (conference/division) details from reference URL"""
        try:
            response = self.session.get(group_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"    Error fetching group: {e}")
            return None

    def fetch_record_details(self, record_url):
        """Fetch team record details from reference URL"""
        try:
            response = self.session.get(record_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"    Error fetching record: {e}")
            return None

    def convert_to_xml(self, teams):
        """Convert teams data to XML format"""
        root = ET.Element("nfl_teams_2025")
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "season").text = "2025"
        ET.SubElement(metadata, "total_teams").text = str(len(teams))
        ET.SubElement(metadata, "generated_date").text = datetime.now().isoformat()
        ET.SubElement(metadata, "source").text = "ESPN API"
        
        # Group teams by conference
        afc_teams = [t for t in teams if 'afc' in t.get('conference', '').lower()]
        nfc_teams = [t for t in teams if 'nfc' in t.get('conference', '').lower()]
        other_teams = [t for t in teams if t not in afc_teams and t not in nfc_teams]
        
        # Add conferences
        for conf_name, conf_teams in [("AFC", afc_teams), ("NFC", nfc_teams), ("Other", other_teams)]:
            if not conf_teams:
                continue
                
            conference = ET.SubElement(root, "conference")
            ET.SubElement(conference, "name").text = conf_name
            ET.SubElement(conference, "team_count").text = str(len(conf_teams))
            
            # Sort teams by division, then by name
            conf_teams.sort(key=lambda x: (x.get('division', ''), x.get('display_name', '')))
            
            for team in conf_teams:
                team_element = ET.SubElement(conference, "team")
                
                # Basic info
                ET.SubElement(team_element, "id").text = str(team.get('id', ''))
                ET.SubElement(team_element, "guid").text = team.get('guid', '')
                ET.SubElement(team_element, "uid").text = team.get('uid', '')
                ET.SubElement(team_element, "name").text = team.get('name', '')
                ET.SubElement(team_element, "display_name").text = team.get('display_name', '')
                ET.SubElement(team_element, "short_display_name").text = team.get('short_display_name', '')
                ET.SubElement(team_element, "nickname").text = team.get('nickname', '')
                ET.SubElement(team_element, "location").text = team.get('location', '')
                ET.SubElement(team_element, "abbreviation").text = team.get('abbreviation', '')
                ET.SubElement(team_element, "color").text = team.get('color', '')
                ET.SubElement(team_element, "alternate_color").text = team.get('alternate_color', '')
                ET.SubElement(team_element, "is_active").text = str(team.get('is_active', True)).lower()
                ET.SubElement(team_element, "division").text = team.get('division', '')
                
                # Logos
                if team.get('logos'):
                    logos_element = ET.SubElement(team_element, "logos")
                    for logo in team['logos']:
                        logo_element = ET.SubElement(logos_element, "logo")
                        ET.SubElement(logo_element, "href").text = logo.get('href', '')
                        ET.SubElement(logo_element, "alt").text = logo.get('alt', '')
                        ET.SubElement(logo_element, "width").text = str(logo.get('width', ''))
                        ET.SubElement(logo_element, "height").text = str(logo.get('height', ''))
                        if logo.get('rel'):
                            rel_element = ET.SubElement(logo_element, "rel")
                            rel_element.text = ','.join(logo['rel']) if isinstance(logo['rel'], list) else str(logo['rel'])
                
                # Venue
                venue = team.get('venue', {})
                if venue:
                    venue_element = ET.SubElement(team_element, "venue")
                    ET.SubElement(venue_element, "id").text = str(venue.get('id', ''))
                    ET.SubElement(venue_element, "name").text = venue.get('name', '')
                    ET.SubElement(venue_element, "capacity").text = str(venue.get('capacity', ''))
                    ET.SubElement(venue_element, "grass").text = str(venue.get('grass', '')).lower()
                    ET.SubElement(venue_element, "city").text = venue.get('city', '')
                    ET.SubElement(venue_element, "state").text = venue.get('state', '')
                
                # Record
                record = team.get('record', {})
                if record:
                    record_element = ET.SubElement(team_element, "record")
                    ET.SubElement(record_element, "wins").text = str(record.get('wins', 0))
                    ET.SubElement(record_element, "losses").text = str(record.get('losses', 0))
                    ET.SubElement(record_element, "ties").text = str(record.get('ties', 0))
                    ET.SubElement(record_element, "percentage").text = str(record.get('percentage', 0.0))
                    ET.SubElement(record_element, "summary").text = record.get('summary', '')
        
        return root

    def prettify_xml(self, elem):
        """Return a pretty-printed XML string"""
        rough_string = ET.tostring(elem, 'unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    def save_xml(self, xml_root, filename=None):
        """Save XML to file in the same directory as the script"""
        script_dir = self.get_script_directory()
        
        if not filename:
            filename = "2025_nfl_teams.xml"
        
        filename = os.path.basename(filename)
        full_path = os.path.join(script_dir, filename)
        
        # Create backup if file exists
        if os.path.exists(full_path):
            backup_path = full_path.replace('.xml', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml')
            try:
                import shutil
                shutil.copy2(full_path, backup_path)
                print(f"📦 Backup created: {os.path.basename(backup_path)}")
            except Exception as e:
                print(f"Warning: Could not create backup: {e}")
        
        xml_string = self.prettify_xml(xml_root)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        
        print(f"XML file saved as: {full_path}")
        return full_path

    def save_json(self, data, filename=None):
        """Save JSON data for backup"""
        script_dir = self.get_script_directory()
        
        if not filename:
            filename = "2025_nfl_teams.json"
        
        filename = os.path.basename(filename)
        full_path = os.path.join(script_dir, filename)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"JSON backup saved as: {full_path}")
        return full_path

    def run(self):
        """Main execution method"""
        print("=" * 60)
        print("ESPN NFL Teams Scraper 2025")
        print("=" * 60)
        
        # Fetch teams list
        print("\n📋 Fetching NFL teams list...")
        teams_data = self.fetch_teams_list()
        
        if not teams_data:
            print("❌ No teams data could be fetched.")
            return False
        
        print(f"✅ Found {len(teams_data)} teams to process")
        
        # Process team data
        print("\n🔄 Processing team details...")
        processed_teams = self.process_team_data(teams_data)
        
        if not processed_teams:
            print("❌ No teams could be processed.")
            return False
        
        print(f"✅ Successfully processed {len(processed_teams)} teams")
        
        # Show summary
        conferences = {}
        for team in processed_teams:
            conf = team.get('conference', 'Unknown')
            if conf not in conferences:
                conferences[conf] = []
            conferences[conf].append(team['display_name'])
        
        print(f"\n📊 Teams by conference:")
        for conf, teams in conferences.items():
            print(f"  {conf}: {len(teams)} teams")
        
        # Save JSON backup
        print("\n💾 Saving JSON backup...")
        json_data = {
            'metadata': {
                'season': 2025,
                'total_teams': len(processed_teams),
                'generated_date': datetime.now().isoformat(),
                'source': 'ESPN API'
            },
            'teams': processed_teams
        }
        json_file = self.save_json(json_data)
        
        # Convert to XML
        print("\n🔄 Converting to XML...")
        xml_root = self.convert_to_xml(processed_teams)
        
        # Save XML file
        print("\n💾 Saving XML file...")
        xml_file = self.save_xml(xml_root)
        
        print(f"\n🎉 Success! Files created:")
        print(f"📄 XML: {xml_file}")
        print(f"📄 JSON: {json_file}")
        print(f"\n📈 Summary: {len(processed_teams)} NFL teams with complete data")
        
        return True

def main():
    """Main function"""
    scraper = NFLTeamsScraper()
    
    try:
        success = scraper.run()
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