import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import time
import os
import re
import matplotlib.pyplot as plt
import seaborn as sns

# Constants
YEARS = [2023, 2024, 2025]
TOURNAMENT_NAME = "att-pebble-beach-pro-am"
# ID Mapping if needed, but R{year}005 seems consistent
BASE_URL = "https://www.pgatour.com/tournaments/{year}/{tournament_name}/R{year}005/course-stats"

def get_url(year):
    return BASE_URL.format(year=year, tournament_name=TOURNAMENT_NAME)

async def fetch_and_parse_rounds(year):
    url = get_url(year)
    print(f"Fetching data for {year} from {url}...")

    rows = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for initial load
            try:
                await page.wait_for_selector("table", timeout=15000)
                # Ensure Pebble Beach is selected
                # Locate the course name text. It might be in a header or button.
                # Based on previous check, we just look for the text in the page content
                # If "Spyglass" is dominant, we might need to switch.
                # But verification showed Pebble is default.
                await page.wait_for_selector("text=Pebble Beach Golf Links", timeout=5000)
            except:
                print(f"Warning: 'Pebble Beach Golf Links' might not be active or table missing for {year}.")

            # Find all round buttons
            # We look for buttons with text "Round <number>"
            # using Playwright locator
            round_buttons = page.locator("button", has_text=re.compile(r"^Round \d+$"))
            count = await round_buttons.count()
            print(f"Found {count} specific round buttons for {year}.")

            # We want to iterate them in order (Round 1, Round 2, ...)
            # Extract text and handle
            buttons_map = {}
            for i in range(count):
                txt = await round_buttons.nth(i).text_content()
                match = re.search(r"Round (\d+)", txt)
                if match:
                    r_num = int(match.group(1))
                    buttons_map[r_num] = round_buttons.nth(i)

            sorted_rounds = sorted(buttons_map.keys())
            print(f"Processing rounds: {sorted_rounds}")

            for r_num in sorted_rounds:
                btn = buttons_map[r_num]
                print(f"  Clicking Round {r_num}...")
                await btn.click()

                # Wait for update.
                # We can wait for the button to be 'active' if there's a class,
                # or just wait a reasonable time for the table to refresh.
                # Since we don't know the exact active class, we use sleep.
                time.sleep(3)

                # Verify we are still on Pebble Beach
                content = await page.content()
                if "Pebble Beach Golf Links" not in content:
                    print("  Warning: Course might have changed! Checking for Spyglass...")
                    if "Spyglass Hill" in content:
                        print("  Detected Spyglass Hill. Attempting to switch back (Not implemented, skipping).")
                        continue

                # Scrape Table
                round_rows = parse_current_table(content, year, r_num)
                if round_rows:
                    print(f"  Extracted {len(round_rows)} rows for Round {r_num}.")
                    rows.extend(round_rows)
                else:
                    print(f"  Failed to parse table for Round {r_num}.")

        except Exception as e:
            print(f"Error fetching {year}: {e}")
        finally:
            await browser.close()

    return rows

def parse_current_table(html, year, round_num):
    soup = BeautifulSoup(html, 'html.parser')

    # Find the stats table
    # We look for the table with "Hole" and "Par" headers
    tables = soup.find_all("table")
    target_table = None

    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Hole" in str(headers) and "Par" in str(headers):
            target_table = table
            break

    if not target_table:
        return []

    rows = []
    tbody = target_table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not cols:
                continue

            # Check for valid hole number (ignore "Out", "In", "Total")
            hole_val = cols[0]
            if hole_val.strip().lower() in ["out", "in", "total"]:
                continue

            try:
                # Column mapping (0: Hole, 1: Par, 3: Avg, 6: Eagles, 7: Birdies, 8: Pars, 9: Bogeys, 10: Dbl+)
                # Verify indices based on inspection
                data = {
                    "Year": year,
                    "Round": round_num,
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
            except (ValueError, IndexError):
                continue

    return rows

async def main():
    all_data = []
    for year in YEARS:
        year_data = await fetch_and_parse_rounds(year)
        all_data.extend(year_data)

    if not all_data:
        print("No data collected.")
        return

    df = pd.DataFrame(all_data)
    csv_filename = "pebble_beach_scoring_history.csv"
    df.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    generate_visualization(df)

def generate_visualization(df):
    if df.empty:
        return

    # Create a Pivot Table for the Heatmap
    # Y-Axis: "Year - Round", X-Axis: "Hole"
    # Value: Avg_Score relative to Par (Avg - Par)

    df['Rel_Score'] = df['Avg_Score'] - df['Par']
    df['Year_Round'] = df['Year'].astype(str) + " - R" + df['Round'].astype(str)

    pivot_df = df.pivot(index="Year_Round", columns="Hole", values="Rel_Score")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_df, cmap="RdBu_r", center=0, annot=True, fmt=".2f",
                cbar_kws={'label': 'Avg Score Relative to Par'})

    plt.title("Pebble Beach Scoring Difficulty (Avg - Par) by Round (2023-2025)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()

    plt.savefig("scoring_fluctuation_heatmap.png")
    print("Visualization saved to scoring_fluctuation_heatmap.png")

if __name__ == "__main__":
    asyncio.run(main())
