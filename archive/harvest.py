import requests
import json
import os
from bs4 import BeautifulSoup

# Example: Scrape title from a website
def scrape_example():
    url = "https://example.com"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    title = soup.title.string.strip()
    return {"site": url, "title": title}

# Example: API request
def get_api_data():
    url = "https://api.example.com/data"
    response = requests.get(url)
    return response.json()

# Save to GitHub-tracked JSON file
def save_to_json(data, filename="data/example.json"):
    os.makedirs("data", exist_ok=True)
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    data = {
        "scraped": scrape_example(),
        "api": get_api_data()
    }
    save_to_json(data)
