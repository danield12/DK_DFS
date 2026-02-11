import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import time
import os
import re
import matplotlib.pyplot as plt
import seaborn as sns
import io
import numpy as np

# Constants
YEARS = [2023, 2024, 2025]
TOURNAMENT_NAME = "att-pebble-beach-pro-am"
BASE_URL = "https://www.pgatour.com/tournaments/{year}/{tournament_name}/R{year}005/course-stats"

# Weather Data with Wind Direction (Degrees)
# Condition_Index: 1=Dry, 2=Damp, 3=Wet
# Wind_Dir_Deg: 0=N, 90=E, 180=S, 270=W
WEATHER_CSV = """Year,Round,Wind_mph,Temp_F,Condition_Index,Wind_Dir_Deg
2023,1,10,55,1,290
2023,2,12,55,2,270
2023,3,20,55,1,180
2023,4,15,52,3,290
2024,1,25,59,3,160
2024,2,25,56,3,160
2024,3,8,55,2,270
2025,1,9,53,1,315
2025,2,8,55,1,315
2025,3,15,57,3,180
2025,4,15,55,3,225"""

# Estimated Hole Azimuths (Tee -> Green Direction in Degrees)
# Based on course orientation:
# 1-3 Inland/West, 4-10 South/Ocean, 11-16 Inland/North/West, 17 West, 18 North along ocean
HOLE_AZIMUTHS = {
    1: 110,  # Inland East
    2: 290,  # Back West
    3: 270,  # West
    4: 180,  # South along ocean
    5: 0,    # North uphill
    6: 180,  # South along ocean
    7: 180,  # South downhill to ocean
    8: 180,  # South along cliff
    9: 180,  # South along cliff
    10: 180, # South along cliff
    11: 45,  # Northeast inland
    12: 270, # West par 3
    13: 0,   # North
    14: 90,  # East par 5
    15: 180, # South
    16: 270, # West
    17: 270, # West to ocean
    18: 340  # Northwest along ocean
}

def load_weather_data():
    return pd.read_csv(io.StringIO(WEATHER_CSV))

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

            try:
                await page.wait_for_selector("table", timeout=15000)
                await page.wait_for_selector("text=Pebble Beach Golf Links", timeout=5000)
            except:
                print(f"Warning: 'Pebble Beach Golf Links' might not be active or table missing for {year}.")

            round_buttons = page.locator("button", has_text=re.compile(r"^Round \d+$"))
            count = await round_buttons.count()
            print(f"Found {count} specific round buttons for {year}.")

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
                time.sleep(3)

                content = await page.content()
                if "Pebble Beach Golf Links" not in content:
                    print("  Warning: Course might have changed! Skipping.")
                    continue

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

            hole_val = cols[0]
            if hole_val.strip().lower() in ["out", "in", "total"]:
                continue

            try:
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

def calculate_wind_components(df):
    """
    Calculates Headwind and Crosswind components.
    Headwind: Wind blowing INTO the hole direction (Positive). Tailwind is Negative.
    Crosswind: Wind blowing across the hole (Absolute value, as left/right both hurt).

    Headwind = Speed * cos(WindDir - HoleDir)
    Crosswind = Speed * |sin(WindDir - HoleDir)|
    Note: Directions are in degrees. Math requires radians.
    """

    # Add Hole Azimuth
    df['Hole_Azimuth'] = df['Hole'].map(HOLE_AZIMUTHS)

    # Calculate Angle Difference (Wind From - Hole To)
    # Wind Direction is "Coming From". Hole Direction is "Going To".
    # Headwind occurs when Wind From (e.g. North 0) meets Hole To (North 0).
    # Wait: Wind Direction "North" usually means blowing FROM North (0 deg) TO South (180 deg).
    # If a hole plays North (0 deg), a North Wind is a HEADWIND.
    # So we want the component of the wind vector opposite to the hole vector?
    # No, Wind Vector direction is (Wind_Dir + 180).
    # Easier: Angle between "Wind From" and "Hole To".
    # If Wind From 0 (North) and Hole To 0 (North), angle diff is 0. Ideally this is Headwind.
    # cos(0) = 1. So Speed * cos(diff) = Positive Headwind. Correct.
    # If Wind From 180 (South) and Hole To 0 (North), angle diff is 180.
    # cos(180) = -1. Tailwind. Correct.

    # Convert to radians
    # Merge HOLE_AZIMUTHS into dataframe first
    df['Hole_Azimuth'] = df['Hole'].map(HOLE_AZIMUTHS)
    df['Angle_Diff_Rad'] = np.radians(df['Wind_Dir_Deg'] - df['Hole_Azimuth'])

    df['Headwind_Comp'] = df['Wind_mph'] * np.cos(df['Angle_Diff_Rad'])
    df['Crosswind_Comp'] = df['Wind_mph'] * np.abs(np.sin(df['Angle_Diff_Rad']))

    return df

async def main():
    # 1. Fetch Scoring Data
    all_data = []
    for year in YEARS:
        year_data = await fetch_and_parse_rounds(year)
        all_data.extend(year_data)

    if not all_data:
        print("No data collected.")
        return

    df_scores = pd.DataFrame(all_data)

    # 2. Merge Weather Data
    df_weather = load_weather_data()
    df_merged = pd.merge(df_scores, df_weather, on=["Year", "Round"], how="left")

    # 3. Calculate Wind Components
    df_analyzed = calculate_wind_components(df_merged)

    # Calculate Relative Score
    df_analyzed['Rel_Score'] = df_analyzed['Avg_Score'] - df_analyzed['Par']

    # 4. Save merged data
    csv_filename = "pebble_beach_scoring_history.csv"
    df_analyzed.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    # 5. Generate Visualizations & Analysis
    analyze_impact(df_analyzed)

def analyze_impact(df):
    if df.empty:
        return

    # Correlation Analysis
    cols_to_corr = ['Wind_mph', 'Temp_F', 'Condition_Index', 'Headwind_Comp', 'Crosswind_Comp', 'Rel_Score']
    correlation = df[cols_to_corr].corr()
    print("\nCorrelation Matrix (Weather Vectors vs Score):")
    print(correlation['Rel_Score'].sort_values(ascending=False))

    # 1. Round-by-Round Fluctuation Heatmap
    df['Year_Round'] = df['Year'].astype(str) + " - R" + df['Round'].astype(str)
    pivot_fluctuation = df.pivot(index="Year_Round", columns="Hole", values="Rel_Score")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_fluctuation, cmap="RdBu_r", center=0, annot=True, fmt=".2f",
                cbar_kws={'label': 'Avg Score Relative to Par'})
    plt.title("Pebble Beach Scoring Difficulty (Avg - Par) by Round (2023-2025)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("scoring_fluctuation_heatmap.png")
    print("Saved scoring_fluctuation_heatmap.png")

    # 2. Headwind vs Score
    plt.figure(figsize=(10, 6))
    sns.regplot(x='Headwind_Comp', y='Rel_Score', data=df, scatter_kws={'alpha':0.5}, line_kws={'color':'red'})
    plt.title("Impact of Headwind Component on Score")
    plt.xlabel("Headwind Component (mph) [+ = Headwind, - = Tailwind]")
    plt.ylabel("Avg Score Relative to Par")
    plt.tight_layout()
    plt.savefig("headwind_impact.png")
    print("Saved headwind_impact.png")

    # 3. Crosswind vs Score
    plt.figure(figsize=(10, 6))
    sns.regplot(x='Crosswind_Comp', y='Rel_Score', data=df, scatter_kws={'alpha':0.5}, line_kws={'color':'purple'})
    plt.title("Impact of Crosswind Component on Score")
    plt.xlabel("Crosswind Component (mph) [Absolute Value]")
    plt.ylabel("Avg Score Relative to Par")
    plt.tight_layout()
    plt.savefig("crosswind_impact.png")
    print("Saved crosswind_impact.png")

    # 4. Wind Speed vs Score (General)
    plt.figure(figsize=(10, 6))
    sns.regplot(x='Wind_mph', y='Rel_Score', data=df, scatter_kws={'alpha':0.5}, line_kws={'color':'blue'})
    plt.title("Impact of Total Wind Speed on Score")
    plt.xlabel("Wind Speed (mph)")
    plt.ylabel("Avg Score Relative to Par")
    plt.tight_layout()
    plt.savefig("wind_vs_score.png")
    print("Saved wind_vs_score.png")

if __name__ == "__main__":
    asyncio.run(main())
