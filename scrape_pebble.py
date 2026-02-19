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

# Refined Weather Data (KMRY - Monterey Regional Airport)
# Wind_Dir_Deg: 0=N, 90=E, 180=S, 270=W
# Note: Wind speeds are average "golf day" sustained winds.
WEATHER_CSV = """Year,Round,Wind_mph,Temp_F,Wind_Dir_Deg
2023,1,12,52,300
2023,2,8,55,290
2023,3,25,50,160
2023,4,12,55,270
2024,1,10,56,225
2024,2,12,54,270
2024,3,10,55,225
2025,1,8,60,315
2025,2,10,58,300
2025,3,15,55,225
2025,4,18,54,200"""

# Precise Azimuths (Tee -> Green Direction in Degrees)
# Derived from ProVisualizer KML data
HOLE_AZIMUTHS = {
    1: 65.95,
    2: 100.86,
    3: 236.83,
    4: 115.76,
    5: 141.19,
    6: 203.78,
    7: 175.93,
    8: 58.70,
    9: 134.73,
    10: 157.03,
    11: 23.85,
    12: 287.27,
    13: 304.60,
    14: 337.92,
    15: 309.07,
    16: 236.08,
    17: 205.55,
    18: 299.62
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
    df['Hole_Azimuth'] = df['Hole'].map(HOLE_AZIMUTHS)
    df['Angle_Diff_Rad'] = np.radians(df['Wind_Dir_Deg'] - df['Hole_Azimuth'])

    # Headwind: Positive = Into Wind, Negative = Downwind
    df['Headwind_Comp'] = df['Wind_mph'] * np.cos(df['Angle_Diff_Rad'])
    # Crosswind: Absolute value
    df['Crosswind_Comp'] = df['Wind_mph'] * np.abs(np.sin(df['Angle_Diff_Rad']))

    return df

def calculate_normalized_stats(df):
    # 1. Percentages
    df['Total_Shots'] = df['Eagles'] + df['Birdies'] + df['Pars'] + df['Bogeys'] + df['Doubles']
    df['Birdie_Better_Pct'] = (df['Eagles'] + df['Birdies']) / df['Total_Shots'] * 100
    df['Bogey_Worse_Pct'] = (df['Bogeys'] + df['Doubles']) / df['Total_Shots'] * 100

    # 2. Normalized Deviation (Relative to Hole Norm and Course Day Norm)
    # Hole Norm: Average score of this hole across all years/rounds in dataset
    hole_stats = df.groupby('Hole')['Avg_Score'].mean().to_dict()
    df['Hole_All_Time_Avg'] = df['Hole'].map(hole_stats)

    # Course Day Norm: Average score relative to par of the entire course for that Round
    # (We can approximate this by averaging the Rel_Score of all holes in that round)
    df['Rel_Score'] = df['Avg_Score'] - df['Par']
    round_stats = df.groupby(['Year', 'Round'])['Rel_Score'].mean().to_dict()

    # Map back to DF
    # We need to map using a tuple key, straightforward way:
    df['Course_Round_Avg_Rel'] = df.apply(lambda x: round_stats.get((x['Year'], x['Round']), 0), axis=1)

    # Global Course Avg Rel (Grand mean of Rel_Score)
    global_course_avg = df['Rel_Score'].mean()

    # Calculation:
    # Deviation = (Hole_Round_Avg - Hole_All_Time_Avg) - (Course_Round_Avg_Rel - Global_Course_Avg_Rel)
    # Interpretation:
    # Part 1: How much harder was this hole today compared to usual? (e.g. +0.5)
    # Part 2: How much harder was the course today compared to usual? (e.g. +0.5)
    # Result: 0.0 (Played "Normal" given the conditions)
    # If Part 1 is +0.2 and Part 2 is +0.5, Result is -0.3 (Played Easier than expected given conditions)

    df['Normalized_Deviation'] = (df['Avg_Score'] - df['Hole_All_Time_Avg']) - (df['Course_Round_Avg_Rel'] - global_course_avg)

    return df

async def main():
    all_data = []
    for year in YEARS:
        year_data = await fetch_and_parse_rounds(year)
        all_data.extend(year_data)

    if not all_data:
        print("No data collected.")
        return

    df_scores = pd.DataFrame(all_data)

    # Merge Weather
    df_weather = load_weather_data()
    df_merged = pd.merge(df_scores, df_weather, on=["Year", "Round"], how="left")

    # Calculations
    df_analyzed = calculate_wind_components(df_merged)
    df_final = calculate_normalized_stats(df_analyzed)

    # Save CSV
    csv_filename = "pebble_beach_scoring_history.csv"
    df_final.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    # Visualizations
    generate_visualizations(df_final)

def generate_visualizations(df):
    if df.empty:
        return

    # Append Wind Speed to the Label for Clarity
    df['Year_Round'] = df['Year'].astype(str) + " - R" + df['Round'].astype(str) + " (" + df['Wind_mph'].astype(str) + " mph)"

    # --- Helper to calculate relative wind arrow ---
    def get_arrow(row):
        # Wind Direction is "From". Hole Azimuth is "Towards".
        # Wind Vector (Blowing Towards): (Wind_Dir + 180) % 360
        # Relative Angle (Push Direction relative to Hole Direction):
        # Rel = (Wind_Vec - Hole_Azimuth) % 360
        wind_push_dir = (row['Wind_Dir_Deg'] + 180) % 360
        rel_angle = (wind_push_dir - row['Hole_Azimuth']) % 360

        # Map to 8 directions
        if 337.5 <= rel_angle or rel_angle < 22.5:
            return "↑"  # Tailwind (Pushing Forward)
        elif 22.5 <= rel_angle < 67.5:
            return "↗"  # Tail/Right
        elif 67.5 <= rel_angle < 112.5:
            return "→"  # Cross Right
        elif 112.5 <= rel_angle < 157.5:
            return "↘"  # Head/Right
        elif 157.5 <= rel_angle < 202.5:
            return "↓"  # Headwind (Pushing Backward)
        elif 202.5 <= rel_angle < 247.5:
            return "↙"  # Head/Left
        elif 247.5 <= rel_angle < 292.5:
            return "←"  # Cross Left
        elif 292.5 <= rel_angle < 337.5:
            return "↖"  # Tail/Left
        return "?"

    df['Wind_Arrow'] = df.apply(get_arrow, axis=1)
    df['Annot_Label'] = df['Rel_Score'].round(2).astype(str) + "\n" + df['Wind_Arrow']

    # 1. Original Rel Score Heatmap (Raw Difficulty) with Wind Arrows
    pivot_raw = df.pivot(index="Year_Round", columns="Hole", values="Rel_Score")
    pivot_annot = df.pivot(index="Year_Round", columns="Hole", values="Annot_Label")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_raw, cmap="RdBu_r", center=0, annot=pivot_annot, fmt="",
                cbar_kws={'label': 'Avg Score Relative to Par'})
    plt.title("Pebble Beach Scoring Difficulty (Avg - Par) & Wind Push Direction (Arrows)\n(↑ = Tailwind, ↓ = Headwind, ←/→ = Crosswind)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("scoring_fluctuation_heatmap.png")

    # 2. Normalized Deviation Heatmap
    # Highlight "Playing Easier/Harder than Normal"
    pivot_norm = df.pivot(index="Year_Round", columns="Hole", values="Normalized_Deviation")
    plt.figure(figsize=(14, 8))
    # Red = Harder than expected, Blue = Easier than expected
    sns.heatmap(pivot_norm, cmap="RdBu_r", center=0, annot=True, fmt=".2f",
                cbar_kws={'label': 'Deviation from Expected Performance'})
    plt.title("Normalized Hole Performance (Adjusted for Hole Avg & Daily Conditions)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("normalized_scoring_heatmap.png")

    # 3. Birdie or Better % Heatmap
    df['Annot_Label_Birdie'] = df['Birdie_Better_Pct'].round(1).astype(str) + "\n" + df['Wind_Arrow']
    pivot_birdie = df.pivot(index="Year_Round", columns="Hole", values="Birdie_Better_Pct")
    pivot_annot_birdie = df.pivot(index="Year_Round", columns="Hole", values="Annot_Label_Birdie")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_birdie, cmap="Greens", annot=pivot_annot_birdie, fmt="",
                cbar_kws={'label': 'Birdie or Better %'})
    plt.title("Birdie or Better Percentage by Round\n(Arrows indicate wind push: ↑ = Tailwind, ↓ = Headwind)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("birdie_better_heatmap.png")

    # 4. Bogey or Worse % Heatmap
    df['Annot_Label_Bogey'] = df['Bogey_Worse_Pct'].round(1).astype(str) + "\n" + df['Wind_Arrow']
    pivot_bogey = df.pivot(index="Year_Round", columns="Hole", values="Bogey_Worse_Pct")
    pivot_annot_bogey = df.pivot(index="Year_Round", columns="Hole", values="Annot_Label_Bogey")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_bogey, cmap="Reds", annot=pivot_annot_bogey, fmt="",
                cbar_kws={'label': 'Bogey or Worse %'})
    plt.title("Bogey or Worse Percentage by Round\n(Arrows indicate wind push: ↑ = Tailwind, ↓ = Headwind)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("bogey_worse_heatmap.png")

    # 5. Wind Impact Correlations
    # Correlate Headwind (Tailwind = Negative) and Crosswind with Birdie/Bogey Pct per Hole

    correlations = []

    for hole, group in df.groupby('Hole'):
        # Headwind (Tailwind is negative Headwind)
        # Correlation: Higher Tailwind (more negative Headwind) -> Higher Birdie %?
        # Expect negative correlation between Headwind and Birdie %
        corr_head_birdie = group['Headwind_Comp'].corr(group['Birdie_Better_Pct'])
        corr_head_bogey = group['Headwind_Comp'].corr(group['Bogey_Worse_Pct'])

        # Crosswind
        # Expect positive correlation between Crosswind and Bogey %?
        corr_cross_birdie = group['Crosswind_Comp'].corr(group['Birdie_Better_Pct'])
        corr_cross_bogey = group['Crosswind_Comp'].corr(group['Bogey_Worse_Pct'])

        correlations.append({
            'Hole': hole,
            'Headwind_Birdie_Corr': corr_head_birdie,
            'Headwind_Bogey_Corr': corr_head_bogey,
            'Crosswind_Birdie_Corr': corr_cross_birdie,
            'Crosswind_Bogey_Corr': corr_cross_bogey
        })

    df_corr = pd.DataFrame(correlations).set_index('Hole')

    # Heatmap: Tailwind Impact (Negative Headwind Correlation)
    # If Corr is negative, it means Higher Headwind -> Lower Birdie % (Or Higher Tailwind -> Higher Birdie %)
    # Let's plot the raw correlation coefficients

    plt.figure(figsize=(14, 6))
    sns.heatmap(df_corr[['Headwind_Birdie_Corr', 'Headwind_Bogey_Corr']].T, cmap="coolwarm", center=0, annot=True, fmt=".2f")
    plt.title("Correlation: Headwind Component vs Scoring (Negative = Tailwind Benefit)")
    plt.xlabel("Hole Number")
    plt.tight_layout()
    plt.savefig("headwind_impact_correlation.png")

    plt.figure(figsize=(14, 6))
    sns.heatmap(df_corr[['Crosswind_Birdie_Corr', 'Crosswind_Bogey_Corr']].T, cmap="coolwarm", center=0, annot=True, fmt=".2f")
    plt.title("Correlation: Crosswind Component vs Scoring")
    plt.xlabel("Hole Number")
    plt.tight_layout()
    plt.savefig("crosswind_impact_correlation.png")

    # 6. Hole Location Impact (Proxy: Normalized Deviation)
    # Assuming residual deviation after accounting for weather/course average is largely due to pin difficulty.
    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_norm, cmap="RdBu_r", center=0, annot=True, fmt=".2f",
                cbar_kws={'label': 'Deviation (Pin Difficulty Proxy)'})
    plt.title("Hole Difficulty Variation (Pin Difficulty Proxy)\n(Residual Score Deviation after Weather Adjustment)")
    plt.xlabel("Hole Number")
    plt.ylabel("Round")
    plt.tight_layout()
    plt.savefig("hole_location_impact_proxy.png")

    print("Saved all visualizations.")

if __name__ == "__main__":
    asyncio.run(main())
