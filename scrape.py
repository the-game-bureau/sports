import http.client
import os
import json

def scrape_tulane_football_news():
    """
    Scrapes Tulane Green Wave football news and data from SportAPI7
    """
    try:
        # Create HTTPS connection
        conn = http.client.HTTPSConnection("sportapi7.p.rapidapi.com")
        
        # Headers for API request
        headers = {
            'x-rapidapi-key': os.getenv('RAPIDAPI_KEY', "0e72ee213amshe68ca7ce87a72c6p1fc079jsna9a45b742de5"),
            'x-rapidapi-host': "sportapi7.p.rapidapi.com"
        }
        
        # Try multiple endpoints for Tulane football data
        endpoints = [
            "/api/v1/sport/american-football/team/tulane/news",
            "/api/v1/sport/american-football/team/tulane/matches",
            "/api/v1/sport/american-football/team/tulane",
            "/api/v1/sport/american-football/teams?search=tulane"
        ]
        
        for endpoint in endpoints:
            print(f"\n=== Trying endpoint: {endpoint} ===")
            try:
                # Make GET request
                conn.request("GET", endpoint, headers=headers)
                
                # Get response
                res = conn.getresponse()
                
                # Check if request was successful
                if res.status == 200:
                    data = res.read()
                    decoded_data = data.decode("utf-8")
                    
                    # Try to parse as JSON for better formatting
                    try:
                        json_data = json.loads(decoded_data)
                        print(f"✓ Success! Data from {endpoint}:")
                        print(json.dumps(json_data, indent=2))
                        print("\n" + "="*50)
                    except json.JSONDecodeError:
                        print(f"✓ Success! Raw data from {endpoint}:")
                        print(decoded_data)
                        print("\n" + "="*50)
                else:
                    print(f"✗ Error: HTTP {res.status} - {res.reason}")
                    
            except Exception as e:
                print(f"✗ Error with endpoint {endpoint}: {e}")
            
            # Create new connection for next request
            conn.close()
            conn = http.client.HTTPSConnection("sportapi7.p.rapidapi.com")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Close connection
        if 'conn' in locals():
            conn.close()

def search_tulane_football():
    """
    Alternative function to search for Tulane football using different approaches
    """
    try:
        conn = http.client.HTTPSConnection("sportapi7.p.rapidapi.com")
        
        headers = {
            'x-rapidapi-key': os.getenv('RAPIDAPI_KEY', "0e72ee213amshe68ca7ce87a72c6p1fc079jsna9a45b742de5"),
            'x-rapidapi-host': "sportapi7.p.rapidapi.com"
        }
        
        # Search endpoints
        search_endpoints = [
            "/api/v1/search?query=tulane+football",
            "/api/v1/search?query=tulane+green+wave",
            "/api/v1/sport/american-football/leagues",
            "/api/v1/sport/american-football"
        ]
        
        for endpoint in search_endpoints:
            print(f"\n=== Searching: {endpoint} ===")
            try:
                conn.request("GET", endpoint, headers=headers)
                res = conn.getresponse()
                
                if res.status == 200:
                    data = res.read()
                    decoded_data = data.decode("utf-8")
                    
                    try:
                        json_data = json.loads(decoded_data)
                        print(f"✓ Found data:")
                        print(json.dumps(json_data, indent=2))
                    except json.JSONDecodeError:
                        print(f"✓ Raw data:")
                        print(decoded_data)
                else:
                    print(f"✗ Error: HTTP {res.status}")
                    
            except Exception as e:
                print(f"✗ Error: {e}")
            
            conn.close()
            conn = http.client.HTTPSConnection("sportapi7.p.rapidapi.com")
            
    except Exception as e:
        print(f"Search error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🏈 TULANE GREEN WAVE FOOTBALL NEWS SCRAPER 🏈")
    print("=" * 50)
    
    print("\n1. Trying direct team endpoints...")
    scrape_tulane_football_news()
    
    print("\n2. Trying search endpoints...")
    search_tulane_football()