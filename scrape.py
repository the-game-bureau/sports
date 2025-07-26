from selenium import webdriver
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.options import Options

# URL of the Tulane 2025 football schedule
url = "https://fbschedules.com/2025-tulane-football-schedule/"

# HTML template with escaped curly braces in CSS
html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>2025 Tulane Football Schedule</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            text-align: center;
        }}
        table {{
            border-collapse: collapse;
            width: 80%;
            margin: 20px auto;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        h1 {{
            color: #0C2340;
        }}
    </style>
</head>
<body>
    <h1>2025 Tulane Football Schedule</h1>
    {table_content}
</body>
</html>
"""

try:
    # Set up headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)

    # Fetch the webpage
    driver.get(url)
    # Wait for page to load (adjust if needed)
    driver.implicitly_wait(10)

    # Parse the HTML with BeautifulSoup
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()

    # Find the schedule table with specific class
    schedule_table = soup.find('table', class_='fbs-table')

    if schedule_table:
        # Convert the table to string, preserving its HTML structure
        table_html = str(schedule_table)
        # Insert the table into the HTML template
        html_content = html_template.format(table_content=table_html)
    else:
        # Fallback if no table is found
        html_content = html_template.format(table_content="<p>Error: Schedule table not found. Check 'debug_page.html' for details.</p>")
        # Log the HTML for debugging
        with open("debug_page.html", "w", encoding="utf-8") as debug_file:
            debug_file.write(soup.prettify())
        print("Debug HTML saved as 'debug_page.html' for inspection.")

except Exception as e:
    # Handle any errors
    html_content = html_template.format(table_content=f"<p>Error: Unable to fetch schedule. ({str(e)})</p>")
    print(f"Error occurred: {str(e)}")

# Save the HTML content to a file
with open("tulane_schedule_2025.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Web page generated as 'tulane_schedule_2025.html'. Open it in a browser to view the schedule.")
print("If the table is not displayed, check 'debug_page.html' to inspect the page content.")