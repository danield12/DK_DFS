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

# Constants
YEARS = [2023, 2024, 2025]
TOURNAMENT_NAME = "att-pebble-beach-pro-am"
BASE_URL = "https://www.pgatour.com/tournaments/{year}/{tournament_name}/R{year}005/course-stats"

# Weather Data (Hardcoded)
# Condition_Index: 1=Dry, 2=Damp, 3=Wet
WEATHER_CSV = """Year,Round,Wind_mph,Temp_F,Condition_Index
2023,1,10,55,1
2023,2,12,55,2
2023,3,20,55,1
2023,4,15,52,3
2024,1,25,59,3
2024,2,25,56,3
2024,3,8,55,2
2025,1,9,53,1
2025,2,8,55,1
2025,3,15,57,3
2025,4,15,55,3"""

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

    # Calculate Relative Score
    df_merged['Rel_Score'] = df_merged['Avg_Score'] - df_merged['Par']

    # 3. Save merged data
    csv_filename = "pebble_beach_scoring_history.csv"
    df_merged.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    # 4. Generate Visualizations & Analysis
    analyze_impact(df_merged)

def analyze_impact(df):
    if df.empty:
        return

    # Correlation Analysis
    cols_to_corr = ['Wind_mph', 'Temp_F', 'Condition_Index', 'Rel_Score']
    correlation = df[cols_to_corr].corr()
    print("\nCorrelation Matrix (Weather vs Score):")
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

    # 2. Wind vs Avg Score (Scatter with Regression)
    plt.figure(figsize=(10, 6))
    sns.regplot(x='Wind_mph', y='Rel_Score', data=df, scatter_kws={'alpha':0.5}, line_kws={'color':'red'})
    plt.title("Impact of Wind Speed on Average Score (Relative to Par)")
    plt.xlabel("Wind Speed (mph)")
    plt.ylabel("Avg Score Relative to Par")
    plt.tight_layout()
    plt.savefig("wind_vs_score.png")
    print("Saved wind_vs_score.png")

    # 3. Temp vs Avg Score
    plt.figure(figsize=(10, 6))
    sns.regplot(x='Temp_F', y='Rel_Score', data=df, scatter_kws={'alpha':0.5}, line_kws={'color':'orange'})
    plt.title("Impact of Temperature on Average Score")
    plt.xlabel("Temperature (F)")
    plt.ylabel("Avg Score Relative to Par")
    plt.tight_layout()
    plt.savefig("temp_vs_score.png")
    print("Saved temp_vs_score.png")

    # 4. Heatmap by Hole and Weather Condition (e.g. Low/High Wind)
    # Categorize Wind: Low (<10), Medium (10-20), High (>20)
    df['Wind_Cat'] = pd.cut(df['Wind_mph'], bins=[-1, 10, 20, 100], labels=['Low (<10mph)', 'Medium (10-20mph)', 'High (>20mph)'])

    pivot_wind = df.pivot_table(index='Hole', columns='Wind_Cat', values='Rel_Score', aggfunc='mean')

    plt.figure(figsize=(12, 8))
    sns.heatmap(pivot_wind, annot=True, cmap="Reds", fmt=".2f")
    plt.title("Average Score Over Par by Hole and Wind Intensity")
    plt.ylabel("Hole Number")
    plt.xlabel("Wind Category")
    plt.tight_layout()
    plt.savefig("hole_wind_impact.png")
    print("Saved hole_wind_impact.png")

if __name__ == "__main__":
    asyncio.run(main())
