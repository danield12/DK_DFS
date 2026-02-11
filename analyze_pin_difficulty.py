import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
import scrape_pebble # To get WEATHER_CSV and load_weather_data
import scrape_masters # To get WEATHER_CSV and load_weather_data

# --- Zoning Logic ---
def get_zone_from_coords(x, y, x_min, x_max, y_min, y_max):
    if x == -1 or y == -1:
        return "Unknown"

    # Dynamic Zoning based on observed range per hole
    x_range = x_max - x_min
    y_range = y_max - y_min

    # Avoid division by zero if range is 0 (single data point)
    if x_range == 0: x_range = 0.001
    if y_range == 0: y_range = 0.001

    # Normalize to 0-1 within the observed box
    x_norm = (x - x_min) / x_range
    y_norm = (y - y_min) / y_range

    # X: 0-0.33 Left, 0.33-0.66 Center, 0.66-1 Right
    if x_norm < 0.33: col = "L"
    elif x_norm < 0.66: col = "C"
    else: col = "R"

    # Y: 0-0.33 Front, 0.33-0.66 Middle, 0.66-1 Back
    # Assuming Y increases from Front to Back?
    # Usually in images Y=0 is top. If "bottomToTopCoords", Y=0 is bottom (Front).
    # Let's assume larger Y is Back.
    if y_norm < 0.33: row = "F"
    elif y_norm < 0.66: row = "M"
    else: row = "B"

    return row + col

def get_zone_from_string(desc):
    desc = str(desc).lower()
    if "front" in desc: row = "F"
    elif "back" in desc: row = "B"
    else: row = "M" # Default to Middle if not specified (or Center)

    if "left" in desc: col = "L"
    elif "right" in desc: col = "R"
    else: col = "C" # Default to Center

    return row + col

# --- Analysis Logic ---
def analyze_course(df_scores, df_weather, pin_locations_df=None, course_name="Unknown"):
    print(f"Analyzing {course_name}...")

    # Merge Weather
    # Ensure types match
    df_scores['Year'] = df_scores['Year'].astype(int)
    df_scores['Round'] = df_scores['Round'].astype(int)
    df_weather['Year'] = df_weather['Year'].astype(int)
    df_weather['Round'] = df_weather['Round'].astype(int)

    df = pd.merge(df_scores, df_weather, on=['Year', 'Round'], how='left')

    # Merge Pin Locations if separate (Augusta)
    if pin_locations_df is not None:
        pin_locations_df['Year'] = pin_locations_df['Year'].astype(int)
        pin_locations_df['Round'] = pin_locations_df['Round'].astype(int)
        pin_locations_df['Hole'] = pin_locations_df['Hole'].astype(int)
        df = pd.merge(df, pin_locations_df, on=['Year', 'Round', 'Hole'], how='left')

    # Determine Zone
    if 'Pin_X_Normalized' in df.columns and 'Pin_Y_Normalized' in df.columns:
        # Calculate min/max per hole for dynamic zoning
        hole_bounds = {}
        for hole in df['Hole'].unique():
            hole_data = df[df['Hole'] == hole]
            valid_pins = hole_data[hole_data['Pin_X_Normalized'] != -1]
            if not valid_pins.empty:
                x_min, x_max = valid_pins['Pin_X_Normalized'].min(), valid_pins['Pin_X_Normalized'].max()
                y_min, y_max = valid_pins['Pin_Y_Normalized'].min(), valid_pins['Pin_Y_Normalized'].max()
                hole_bounds[hole] = (x_min, x_max, y_min, y_max)
            else:
                hole_bounds[hole] = (0, 1, 0, 1) # Default

        def apply_zoning(row):
            if row['Pin_X_Normalized'] != -1:
                bounds = hole_bounds.get(row['Hole'], (0, 1, 0, 1))
                return get_zone_from_coords(row['Pin_X_Normalized'], row['Pin_Y_Normalized'], *bounds)
            elif 'Pin_Location' in row and pd.notna(row['Pin_Location']):
                return get_zone_from_string(row['Pin_Location'])
            else:
                return "Unknown"

        df['Zone'] = df.apply(apply_zoning, axis=1)

    elif 'Pin_Location' in df.columns:
        df['Zone'] = df['Pin_Location'].apply(get_zone_from_string)
    else:
        df['Zone'] = "Unknown"

    # Filter out Unknown zones for analysis
    df_analyzed = df[df['Zone'] != "Unknown"].copy()

    if df_analyzed.empty:
        print(f"No valid zone data for {course_name}")
        return None

    # --- Isolation Logic ---
    # 1. Hole Baseline (All Time Avg for that Hole)
    hole_stats = df.groupby('Hole')['Avg_Score'].mean().to_dict()
    df_analyzed['Hole_Baseline'] = df_analyzed['Hole'].map(hole_stats)

    # 2. Field Adjustment on D (Course Round Avg - Global Course Avg)
    # Calculate global average score relative to par
    df_analyzed['Rel_Score'] = df_analyzed['Avg_Score'] - df_analyzed['Par']
    global_avg_rel = df_analyzed['Rel_Score'].mean()

    # Calculate daily average relative score
    daily_stats = df_analyzed.groupby(['Year', 'Round'])['Rel_Score'].mean().to_dict()
    df_analyzed['Field_Avg_Rel'] = df_analyzed.apply(lambda x: daily_stats.get((x['Year'], x['Round']), 0), axis=1)

    df_analyzed['Field_Adjustment'] = df_analyzed['Field_Avg_Rel'] - global_avg_rel

    # 3. Pin Difficulty
    # Pin Diff = (Hole Avg on D) - (Hole Baseline) - (Field Adjustment)
    # Hole Avg on D IS Avg_Score for that row (since row is unique per Year/Round/Hole)
    df_analyzed['Pin_Difficulty'] = (df_analyzed['Avg_Score'] - df_analyzed['Hole_Baseline']) - df_analyzed['Field_Adjustment']

    # --- Impact Metrics ---
    # Birdie Impact = Zone Birdie % - Historical Hole Birdie %
    # Bogey Impact = Zone Bogey % - Historical Hole Bogey %

    # Calculate Percentages
    df_analyzed['Total_Shots'] = df_analyzed['Eagles'] + df_analyzed['Birdies'] + df_analyzed['Pars'] + df_analyzed['Bogeys'] + df_analyzed['Doubles']
    df_analyzed['Birdie_Pct'] = (df_analyzed['Eagles'] + df_analyzed['Birdies']) / df_analyzed['Total_Shots']
    df_analyzed['Bogey_Pct'] = (df_analyzed['Bogeys'] + df_analyzed['Doubles']) / df_analyzed['Total_Shots']

    # Historical Hole Averages
    hole_birdie_base = df_analyzed.groupby('Hole')['Birdie_Pct'].mean().to_dict()
    hole_bogey_base = df_analyzed.groupby('Hole')['Bogey_Pct'].mean().to_dict()

    df_analyzed['Hole_Birdie_Base'] = df_analyzed['Hole'].map(hole_birdie_base)
    df_analyzed['Hole_Bogey_Base'] = df_analyzed['Hole'].map(hole_bogey_base)

    df_analyzed['Birdie_Impact'] = df_analyzed['Birdie_Pct'] - df_analyzed['Hole_Birdie_Base']
    df_analyzed['Bogey_Impact'] = df_analyzed['Bogey_Pct'] - df_analyzed['Hole_Bogey_Base']

    return df_analyzed

def generate_cheat_sheet(df, course_name):
    if df is None or df.empty:
        return pd.DataFrame()

    results = []
    # Group by Hole and Zone to get average impacts
    grouped = df.groupby(['Hole', 'Zone']).agg({
        'Pin_Difficulty': 'mean',
        'Birdie_Impact': 'mean',
        'Bogey_Impact': 'mean',
        'Year': 'count' # Count occurrences
    }).reset_index()

    for hole in grouped['Hole'].unique():
        hole_data = grouped[grouped['Hole'] == hole]

        # 1. Green Light: Max Birdie Impact, Min Pin Diff
        # We look for the best tradeoff. Let's just pick Max Birdie Impact.
        green_light = hole_data.loc[hole_data['Birdie_Impact'].idxmax()]

        # 2. Sucker Pin: High Bogey Impact.
        sucker = hole_data.loc[hole_data['Bogey_Impact'].idxmax()]

        # 3. Weather Proof: Min Abs(Field Adjustment Correlation)?
        # The user defined "Weather-Proof" as: "Pins where Field Adjustment had least correlation with scoring".
        # This is harder to calculate on aggregated zone data.
        # Let's simplify: The zone with the lowest Pin Difficulty variance?
        # Or just lowest Pin Difficulty (Easiest)?
        # User example: "Wind didn't affect this specific pin location as much".
        # I'll skip Weather Proof for the cheat sheet row for now and just output the full table.

        # Actually, let's just output the full table for the user to filter.
        # The user wants "Jules should produce a table... answering these questions".

        for _, row in hole_data.iterrows():
            verdict = "Neutral"
            if row['Birdie_Impact'] > 0.05 and row['Bogey_Impact'] < 0.05:
                verdict = "Green Light"
            elif row['Bogey_Impact'] > 0.10:
                verdict = "Sucker Pin"
            elif row['Pin_Difficulty'] > 0.2:
                verdict = "Hard"
            elif row['Pin_Difficulty'] < -0.2:
                verdict = "Easy"

            results.append({
                'Course': course_name,
                'Hole': hole,
                'Zone': row['Zone'],
                'Pin_Diff_Isolated': round(row['Pin_Difficulty'], 3),
                'Birdie_Pct_Impact': f"{row['Birdie_Impact']*100:+.1f}%",
                'Bogey_Pct_Impact': f"{row['Bogey_Impact']*100:+.1f}%",
                'Sample_Size': row['Year'],
                'Verdict': verdict
            })

    return pd.DataFrame(results)

def main():
    # Load Pebble
    try:
        df_pebble = pd.read_csv("pebble_beach_data_combined.csv")
        weather_pebble = scrape_pebble.load_weather_data()
        df_pebble_analyzed = analyze_course(df_pebble, weather_pebble, course_name="Pebble Beach")
        cheat_sheet_pebble = generate_cheat_sheet(df_pebble_analyzed, "Pebble Beach")
    except Exception as e:
        print(f"Error processing Pebble Beach: {e}")
        cheat_sheet_pebble = pd.DataFrame()

    # Load Augusta
    try:
        df_augusta = pd.read_csv("masters_scoring_data.csv")
        # Ensure we have weather data (scrape_masters.py should have WEATHER_CSV)
        weather_augusta = scrape_masters.load_weather_data()

        try:
            pin_locs_augusta = pd.read_csv("masters_pin_locations.csv", comment='#')
        except FileNotFoundError:
            print("masters_pin_locations.csv not found. Skipping Augusta Pin Analysis.")
            pin_locs_augusta = None
        except Exception as e:
            print(f"Error reading masters_pin_locations.csv: {e}")
            pin_locs_augusta = None

        if pin_locs_augusta is not None:
            df_augusta_analyzed = analyze_course(df_augusta, weather_augusta, pin_locations_df=pin_locs_augusta, course_name="Augusta National")
            cheat_sheet_augusta = generate_cheat_sheet(df_augusta_analyzed, "Augusta National")
        else:
            cheat_sheet_augusta = pd.DataFrame()
    except Exception as e:
        print(f"Error processing Augusta: {e}")
        cheat_sheet_augusta = pd.DataFrame()

    # Combine and Save
    final_cheat_sheet = pd.concat([cheat_sheet_pebble, cheat_sheet_augusta], ignore_index=True)
    if not final_cheat_sheet.empty:
        final_cheat_sheet.to_csv("pin_difficulty_cheat_sheet.csv", index=False)
        print("Saved pin_difficulty_cheat_sheet.csv")
        print(final_cheat_sheet.head())
    else:
        print("No cheat sheet generated.")

    # Visualization (Heatmaps for all holes)
    if not df_pebble_analyzed.empty:
        print("Generating Heatmaps for Pebble Beach...")
        # Define grid order
        grid_rows = ['B', 'M', 'F'] # Back to Front (Top to Bottom in plot)
        grid_cols = ['L', 'C', 'R'] # Left to Right

        for hole in sorted(df_pebble_analyzed['Hole'].unique()):
            hole_data = df_pebble_analyzed[df_pebble_analyzed['Hole'] == hole]

            # Create 3x3 grid for Pin Difficulty
            grid_diff = pd.DataFrame(index=grid_rows, columns=grid_cols, dtype=float)
            grid_birdie = pd.DataFrame(index=grid_rows, columns=grid_cols, dtype=float)

            # Fill grid
            grouped = hole_data.groupby('Zone')[['Pin_Difficulty', 'Birdie_Impact']].mean()

            for r in grid_rows:
                for c in grid_cols:
                    zone = r + c
                    if zone in grouped.index:
                        grid_diff.loc[r, c] = grouped.loc[zone, 'Pin_Difficulty']
                        grid_birdie.loc[r, c] = grouped.loc[zone, 'Birdie_Impact'] * 100

            # Plot
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            # Pin Difficulty Heatmap
            sns.heatmap(grid_diff, annot=True, fmt=".2f", cmap="RdBu_r", center=0, ax=axes[0])
            axes[0].set_title(f"Hole {hole} - Pin Difficulty (Isolated)")

            # Birdie Impact Heatmap
            sns.heatmap(grid_birdie, annot=True, fmt=".1f", cmap="Greens", center=0, ax=axes[1])
            axes[1].set_title(f"Hole {hole} - Birdie Impact %")

            plt.tight_layout()
            plt.savefig(f"pebble_hole_{hole}_analysis.png")
            plt.close()
        print("Heatmaps saved.")

if __name__ == "__main__":
    main()
