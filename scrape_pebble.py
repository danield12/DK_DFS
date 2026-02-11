import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import time
import os
import matplotlib.pyplot as plt
import seaborn as sns

# Constants
YEARS = [2023, 2024, 2025]
TOURNAMENT_NAME = "att-pebble-beach-pro-am"
# Updated URL pattern based on 2025 finding
# The tournament ID seems to be R{year}005. Let's verify if it's consistent.
# 2025: R2025005
# 2024: R2024005 (assumed)
# 2023: R2023005 (assumed)
BASE_URL = "https://www.pgatour.com/tournaments/{year}/{tournament_name}/R{year}005/course-stats"

def get_url(year):
    return BASE_URL.format(year=year, tournament_name=TOURNAMENT_NAME)

async def fetch_html(year):
    url = get_url(year)
    print(f"Fetching data for {year} from {url}...")

    async with async_playwright() as p:
        # Use a realistic user agent
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for the table to appear
            # The table seems to be rendered client-side or at least needs time
            try:
                await page.wait_for_selector("table", timeout=15000)
                print("Table selector found.")
            except:
                print("Table selector not found immediately, waiting a bit more...")
                time.sleep(5)

            # Scroll down to ensure lazy loaded content is present
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            content = await page.content()
            return content

        except Exception as e:
            print(f"Error fetching {year}: {e}")
            return None
        finally:
            await browser.close()

def parse_html(html, year):
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    # Verify course name
    # We look for "Pebble Beach Golf Links" in the text near the table
    # Or just ensure it's on the page and assume default behavior as verified
    if "Pebble Beach Golf Links" not in soup.get_text():
        print(f"Warning: 'Pebble Beach Golf Links' not found in page text for {year}. Skipping.")
        return None

    # Find the table
    # Based on previous inspection, there is one table and it follows "Hole Stats"
    # Or simply find the table with the specific headers
    tables = soup.find_all("table")
    target_table = None

    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        # Check for key columns
        if "Hole" in str(headers) and "Par" in headers and "eagles" in headers:
            target_table = table
            break

    if not target_table:
        print(f"Stats table not found for {year}.")
        return None

    # Extract rows
    rows = []
    tbody = target_table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not cols:
                continue

            # Columns mapping based on 2025 inspection:
            # 0: Hole, 1: Par, 2: Yards, 3: Avg, 4: Rank, 5: +/-, 6: Eagles, 7: Birdies, 8: Pars, 9: Bogeys, 10: Dbl+
            # We want: Year, Hole, Par, Avg_Score, Eagles, Birdies, Pars, Bogeys, Doubles

            hole_val = cols[0]
            # Skip summary rows (case-insensitive)
            if hole_val.strip().lower() in ["out", "in", "total"]:
                continue

            try:
                data = {
                    "Year": year,
                    "Hole": int(hole_val),
                    "Par": int(cols[1]),
                    "Avg_Score": float(cols[3]),
                    "Eagles": int(cols[6]),
                    "Birdies": int(cols[7]),
                    "Pars": int(cols[8]),
                    "Bogeys": int(cols[9]),
                    "Doubles": int(cols[10])
                }
                rows.append(data)
            except (ValueError, IndexError) as e:
                print(f"Error parsing row for hole {hole_val}: {e}")
                continue

    return rows

async def main():
    all_data = []

    for year in YEARS:
        html = await fetch_html(year)
        if html:
            rows = parse_html(html, year)
            if rows:
                print(f"Extracted {len(rows)} rows for {year}.")
                all_data.extend(rows)
            else:
                print(f"No data parsed for {year}.")
        else:
            print(f"Failed to fetch HTML for {year}.")

    if not all_data:
        print("No data collected.")
        return

    # Create DataFrame
    df = pd.DataFrame(all_data)

    # Save to CSV
    csv_filename = "pebble_beach_scoring_history.csv"
    df.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    # Visualization
    generate_heatmap(df)

def generate_heatmap(df):
    if df.empty:
        return

    # Pivot data for heatmap: Holes vs Score Type (summed over years or average?)
    # Requirement: "Holes vs. Score Type"
    # Since we have 3 years, we can aggregate (sum) the counts for each hole.

    # Group by Hole and sum the counts
    agg_df = df.groupby("Hole")[["Eagles", "Birdies", "Pars", "Bogeys", "Doubles"]].sum()

    # We can also calculate percentages if needed, but counts are fine.
    # Requirement says "count or percentage". Let's do percentage for better visualization
    # because the total shots per hole might vary.

    pct_df = agg_df.div(agg_df.sum(axis=1), axis=0) * 100

    plt.figure(figsize=(12, 8))
    sns.heatmap(pct_df, annot=True, fmt=".1f", cmap="YlGnBu", cbar_kws={'label': 'Percentage (%)'})
    plt.title("Scoring Distribution by Hole - Pebble Beach Golf Links (2023-2025)")
    plt.xlabel("Score Type")
    plt.ylabel("Hole Number")
    plt.tight_layout()

    plt.savefig("scoring_heatmap.png")
    print("Heatmap saved to scoring_heatmap.png")

if __name__ == "__main__":
    asyncio.run(main())
