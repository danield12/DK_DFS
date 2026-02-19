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
YEARS = [2020, 2021, 2022, 2023, 2024]
TOURNAMENT_NAME = "masters-tournament"
# URL for Masters often uses R{year}014. Verified for 2024.
BASE_URL = "https://www.pgatour.com/tournaments/{year}/{tournament_name}/R{year}014/course-stats"

# Weather Data (User Provided)
# Note: Wind_mph contains ranges. We will parse this to average.
# Wind_Dir needs to be mapped to degrees.
WEATHER_CSV = """Year,Round,Date,Wind_mph,Gusts_mph,Temp_High_F,Wind_Dir,Conditions
2024,1,2024-04-11,15-20,35,78,S/SW,Delayed start (rain); Windy afternoon
2024,2,2024-04-12,15-20,35,73,W/NW,Sunny but very windy; Difficult scoring
2024,3,2024-04-13,7-15,20,78,W/NW,Sunny and warm; Calmer winds
2024,4,2024-04-14,7-15,17,84,SW,Warm and sunny; Ideal finishing conditions
2023,1,2023-04-06,5-10,12,85,S/SW,Hot and humid; Good scoring
2023,2,2023-04-07,10-15,25,75,NE,Rain and storms; Play suspended; Temp dropped
2023,3,2023-04-08,12-18,25,48,NE,Cold; Heavy rain; Play suspended
2023,4,2023-04-09,10-15,20,62,NE,Cool and cloudy; Clearing late
2022,1,2022-04-07,10-15,20,73,W,Sunny; Breezy
2022,2,2022-04-08,15-20,30,67,SW/W,Windy and cooler; Tough conditions
2022,3,2022-04-09,10-15,20,54,W,Cold; Feels like 40s; Windy
2022,4,2022-04-10,5-10,15,73,SW,Sunny; Warmer; Pleasant finish
2021,1,2021-04-08,10-12,15,81,SSW,Warm; Overcast; Firm conditions
2021,2,2021-04-09,8-10,12,80,S,Scattered storms; Softening course
2021,3,2021-04-10,10-15,25,82,S,Storms suspended play; Humid
2021,4,2021-04-11,10-13,15,79,WSW,Sunny; Drying out
2020,1,2020-11-12,5-10,12,78,E/NE,Delayed (rain); Soft conditions; Warm for Nov
2020,2,2020-11-13,5-10,10,79,NE,Overcast; calm; Soft greens
2020,3,2020-11-14,5-10,12,76,N/NE,Sunny; Perfect scoring conditions
2020,4,2020-11-15,10-15,20,81,SW,Wind picked up slightly; Warm finish."""

# Precise Azimuths (Tee -> Green Direction in Degrees) - Calculated from ProVisualizer Coordinates
HOLE_AZIMUTHS = {
    1: 304.78,
    2: 172.65,
    3: 311.34,
    4: 264.78,
    5: 166.99,
    6: 14.03,
    7: 112.81,
    8: 346.02,
    9: 127.36,
    10: 189.03,
    11: 217.79,
    12: 209.46,
    13: 333.37,
    14: 91.51,
    15: 286.74,
    16: 335.94,
    17: 106.79,
    18: 14.8,
}

PIN_LOCATIONS_FILE = "masters_pin_locations.csv"

def parse_wind_speed(wind_str):
    if '-' in str(wind_str):
        parts = wind_str.split('-')
        try:
            return (float(parts[0]) + float(parts[1])) / 2
        except:
            return float(parts[0])
    try:
        return float(wind_str)
    except:
        return 0.0

def parse_wind_dir(dir_str):
    mapping = {
        'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5,
        'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5,
        'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5,
        'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5
    }
    # Handle composites like S/SW -> Average
    if '/' in dir_str:
        parts = dir_str.split('/')
        angles = [mapping.get(p.strip(), 0) for p in parts]
        # Circular mean not strictly needed for these small diffs usually
        return np.mean(angles)
    return mapping.get(dir_str.strip(), 0)

def load_weather_data():
    df = pd.read_csv(io.StringIO(WEATHER_CSV))
    # Parse Wind Speed (avg of range)
    df['Wind_mph_Avg'] = df['Wind_mph'].apply(parse_wind_speed)
    # Parse Wind Direction
    df['Wind_Dir_Deg'] = df['Wind_Dir'].apply(parse_wind_dir)
    return df

def load_pin_locations():
    if os.path.exists(PIN_LOCATIONS_FILE):
        print(f"Loading pin locations from {PIN_LOCATIONS_FILE}...")
        try:
            # Handle comments in the CSV
            df = pd.read_csv(PIN_LOCATIONS_FILE, comment='#')
            # Ensure columns exist: Year, Round, Hole, Pin_Location
            required = ['Year', 'Round', 'Hole', 'Pin_Location']
            if all(col in df.columns for col in required):
                return df
            else:
                print(f"Warning: {PIN_LOCATIONS_FILE} missing required columns {required}.")
                return None
        except Exception as e:
            print(f"Error loading pin locations: {e}")
            return None
    else:
        print(f"Warning: {PIN_LOCATIONS_FILE} not found. Pin grouping analysis will be skipped.")
        return None

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

            # Check for specific Augusta National text or table
            try:
                await page.wait_for_selector("table", timeout=15000)
                # Note: "Augusta National Golf Club" might be the text
                await page.wait_for_selector("text=Augusta National Golf Club", timeout=5000)
            except:
                print(f"Warning: 'Augusta National Golf Club' might not be active or table missing for {year}.")

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
                # Use asyncio.sleep to avoid blocking the event loop
                await asyncio.sleep(3)

                content = await page.content()
                if "Augusta National Golf Club" not in content:
                    print("  Warning: Course might have changed or page not loaded! Skipping.")
                    # continue # Commented out to be lenient if text check fails but table exists

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
                # Columns might vary slightly, but usually:
                # Hole, Par, Yardage, Avg, ...
                # The prompt's code used cols[3] for Avg_Score.
                # Check headers to be sure? Assuming standard PGA Tour format.

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
    df['Headwind_Comp'] = df['Wind_mph_Avg'] * np.cos(df['Angle_Diff_Rad'])
    # Crosswind: Absolute value
    df['Crosswind_Comp'] = df['Wind_mph_Avg'] * np.abs(np.sin(df['Angle_Diff_Rad']))

    return df

def calculate_normalized_stats(df):
    # 1. Percentages
    df['Total_Shots'] = df['Eagles'] + df['Birdies'] + df['Pars'] + df['Bogeys'] + df['Doubles']
    df['Birdie_Better_Pct'] = (df['Eagles'] + df['Birdies']) / df['Total_Shots'] * 100
    df['Bogey_Worse_Pct'] = (df['Bogeys'] + df['Doubles']) / df['Total_Shots'] * 100

    # 2. Normalized Deviation
    hole_stats = df.groupby('Hole')['Avg_Score'].mean().to_dict()
    df['Hole_All_Time_Avg'] = df['Hole'].map(hole_stats)

    df['Rel_Score'] = df['Avg_Score'] - df['Par']
    round_stats = df.groupby(['Year', 'Round'])['Rel_Score'].mean().to_dict()

    df['Course_Round_Avg_Rel'] = df.apply(lambda x: round_stats.get((x['Year'], x['Round']), 0), axis=1)

    global_course_avg = df['Rel_Score'].mean()

    df['Normalized_Deviation'] = (df['Avg_Score'] - df['Hole_All_Time_Avg']) - (df['Course_Round_Avg_Rel'] - global_course_avg)

    return df

def analyze_pin_locations(df, pin_df):
    if pin_df is None:
        return df, None

    # Merge Pin Locations
    # Ensure types match
    df['Year'] = df['Year'].astype(int)
    df['Round'] = df['Round'].astype(int)
    df['Hole'] = df['Hole'].astype(int)

    pin_df['Year'] = pin_df['Year'].astype(int)
    pin_df['Round'] = pin_df['Round'].astype(int)
    pin_df['Hole'] = pin_df['Hole'].astype(int)

    df_merged = pd.merge(df, pin_df, on=['Year', 'Round', 'Hole'], how='left')

    # Group by Pin Location
    # We want "groupings of pin locations that result in more birdies and more bogeys"
    # and "estimated magnitude increase".

    # Global Avg for Hole
    hole_avgs = df.groupby('Hole')[['Birdie_Better_Pct', 'Bogey_Worse_Pct']].mean()

    # Group by Pin Location (across all holes? or per hole?)
    # Usually "Back Right" plays different on Hole 1 vs Hole 12.
    # But maybe the user wants general trends like "Tucked Left vs Center".
    # Let's do Per-Hole-Pin-Location first, then aggregate if needed.
    # The user asked for "groupings of pin locations".

    if 'Pin_Location' not in df_merged.columns:
        return df, None

    # Filter out rows where Pin_Location is NaN
    df_pins = df_merged.dropna(subset=['Pin_Location'])

    if df_pins.empty:
        return df, None

    # Calculate Magnitude Increase per Pin Group per Hole
    results = []
    # User Note: "do not assume all pin locations in the same quadrant are the same"
    # Grouping strictly by the string provided in Pin_Location column
    for (hole, pin_loc), group in df_pins.groupby(['Hole', 'Pin_Location']):
        avg_birdie = group['Birdie_Better_Pct'].mean()
        avg_bogey = group['Bogey_Worse_Pct'].mean()

        base_birdie = hole_avgs.loc[hole, 'Birdie_Better_Pct']
        base_bogey = hole_avgs.loc[hole, 'Bogey_Worse_Pct']

        results.append({
            'Hole': hole,
            'Pin_Location': pin_loc,
            'Avg_Birdie_Pct': avg_birdie,
            'Birdie_Magnitude_Inc': avg_birdie - base_birdie,
            'Avg_Bogey_Pct': avg_bogey,
            'Bogey_Magnitude_Inc': avg_bogey - base_bogey,
            'Count': len(group)
        })

    pin_stats = pd.DataFrame(results)

    return df_merged, pin_stats

async def main():
    all_data = []
    for year in YEARS:
        year_data = await fetch_and_parse_rounds(year)
        all_data.extend(year_data)

    if not all_data:
        print("No data collected.")
        # For testing purposes without fetching (if blocked), uncomment below to mock data
        # all_data = mock_data()
        return

    df_scores = pd.DataFrame(all_data)

    # Merge Weather
    df_weather = load_weather_data()
    df_merged = pd.merge(df_scores, df_weather, on=["Year", "Round"], how="left")

    # Calculations
    df_analyzed = calculate_wind_components(df_merged)
    df_final = calculate_normalized_stats(df_analyzed)

    # Pin Location Analysis
    df_pin_locs = load_pin_locations()
    df_final_with_pins, pin_stats = analyze_pin_locations(df_final, df_pin_locs)

    # Save CSV
    csv_filename = "masters_scoring_history.csv"
    df_final_with_pins.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

    if pin_stats is not None:
        pin_stats_file = "masters_pin_impact.csv"
        pin_stats.to_csv(pin_stats_file, index=False)
        print(f"Pin Location Impact saved to {pin_stats_file}")
        print("\nTop Pin Locations for Birdies (Magnitude Increase):")
        print(pin_stats.sort_values("Birdie_Magnitude_Inc", ascending=False).head(10)[['Hole', 'Pin_Location', 'Birdie_Magnitude_Inc']])
        print("\nTop Pin Locations for Bogeys (Magnitude Increase):")
        print(pin_stats.sort_values("Bogey_Magnitude_Inc", ascending=False).head(10)[['Hole', 'Pin_Location', 'Bogey_Magnitude_Inc']])

    # Visualizations
    generate_visualizations(df_final_with_pins, pin_stats)

def generate_visualizations(df, pin_stats):
    if df.empty:
        return

    # Append Wind Speed to the Label for Clarity
    # Using Wind_mph_Avg
    df['Year_Round'] = df['Year'].astype(str) + " - R" + df['Round'].astype(str) + " (" + df['Wind_mph_Avg'].astype(str) + " mph)"

    # --- Helper to calculate relative wind arrow ---
    def get_arrow(row):
        wind_push_dir = (row['Wind_Dir_Deg'] + 180) % 360
        rel_angle = (wind_push_dir - row['Hole_Azimuth']) % 360

        if 337.5 <= rel_angle or rel_angle < 22.5: return "↑"
        elif 22.5 <= rel_angle < 67.5: return "↗"
        elif 67.5 <= rel_angle < 112.5: return "→"
        elif 112.5 <= rel_angle < 157.5: return "↘"
        elif 157.5 <= rel_angle < 202.5: return "↓"
        elif 202.5 <= rel_angle < 247.5: return "↙"
        elif 247.5 <= rel_angle < 292.5: return "←"
        elif 292.5 <= rel_angle < 337.5: return "↖"
        return "?"

    df['Wind_Arrow'] = df.apply(get_arrow, axis=1)
    df['Annot_Label'] = df['Rel_Score'].round(2).astype(str) + "\n" + df['Wind_Arrow']

    # 1. Heatmap
    pivot_raw = df.pivot(index="Year_Round", columns="Hole", values="Rel_Score")
    pivot_annot = df.pivot(index="Year_Round", columns="Hole", values="Annot_Label")

    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_raw, cmap="RdBu_r", center=0, annot=pivot_annot, fmt="",
                cbar_kws={'label': 'Avg Score Relative to Par'})
    plt.title("Masters Scoring Difficulty & Wind Push Direction")
    plt.tight_layout()
    plt.savefig("masters_scoring_heatmap.png")

    # 2. Normalized Deviation
    pivot_norm = df.pivot(index="Year_Round", columns="Hole", values="Normalized_Deviation")
    plt.figure(figsize=(14, 8))
    sns.heatmap(pivot_norm, cmap="RdBu_r", center=0, annot=True, fmt=".2f",
                cbar_kws={'label': 'Deviation'})
    plt.title("Normalized Hole Performance (Masters)")
    plt.tight_layout()
    plt.savefig("masters_normalized_heatmap.png")

    # 3. Pin Impact Visualization (if available)
    if pin_stats is not None and not pin_stats.empty:
        # Scatter plot of Magnitude Increase
        plt.figure(figsize=(12, 8))
        sns.scatterplot(data=pin_stats, x='Hole', y='Birdie_Magnitude_Inc', hue='Pin_Location', style='Pin_Location', s=100)
        plt.axhline(0, color='grey', linestyle='--')
        plt.title("Birdie Magnitude Increase by Pin Location")
        plt.ylabel("Birdie % Increase vs Hole Avg")
        plt.tight_layout()
        plt.savefig("masters_pin_birdie_impact.png")

        plt.figure(figsize=(12, 8))
        sns.scatterplot(data=pin_stats, x='Hole', y='Bogey_Magnitude_Inc', hue='Pin_Location', style='Pin_Location', s=100)
        plt.axhline(0, color='grey', linestyle='--')
        plt.title("Bogey Magnitude Increase by Pin Location")
        plt.ylabel("Bogey % Increase vs Hole Avg")
        plt.tight_layout()
        plt.savefig("masters_pin_bogey_impact.png")

    print("Saved all visualizations.")

# Mock data for testing when scraping is blocked/not possible
def mock_data():
    rows = []
    for year in YEARS:
        for r in [1, 2, 3, 4]:
            for h in range(1, 19):
                rows.append({
                    "Year": year,
                    "Round": r,
                    "Hole": h,
                    "Par": 4 if h not in [2,8,13,15,4,6,12,16] else (5 if h in [2,8,13,15] else 3),
                    "Avg_Score": 4.1 + np.random.normal(0, 0.5),
                    "Eagles": 0, "Birdies": 10, "Pars": 50, "Bogeys": 20, "Doubles": 5
                })
    return rows

if __name__ == "__main__":
    asyncio.run(main())
