# AT&T Pebble Beach Pro-Am Scoring & Weather Analysis

This project scrapes **round-level** hole-by-hole scoring data for the **Pebble Beach Golf Links** course from the **AT&T Pebble Beach Pro-Am** tournament (2023, 2024, 2025) and integrates robust historical weather data to analyze the impact of conditions on scoring.

## Data Source
- **Scoring Data:** Scraped from [PGATour.com](https://www.pgatour.com) using `playwright` to interact with the Next.js application.
- **Weather Data:** Sourced from **Monterey Regional Airport (KMRY)** historical records (via Aviation Weather/WeatherSpark) for the specific dates and hours of play.
- **Course Data:** Estimated Hole Azimuths (Tee-to-Green direction) for wind vector analysis.

## Files
- `scrape_pebble.py`: Main script to scrape data, merge weather, calculate vectors, and generate visualizations.
- `pebble_beach_scoring_history.csv`: Aggregated scoring data including:
  - `Headwind_Comp`: Positive = Into Wind, Negative = Downwind.
  - `Crosswind_Comp`: Absolute lateral wind component.
  - `Normalized_Deviation`: Deviation of hole score from expected (adjusted for hole avg and course day difficulty).
- `normalized_scoring_heatmap.png`: Heatmap showing which holes played easier/harder than expected relative to "normal".
- `birdie_better_heatmap.png`: % of Birdie or Better scores per hole/round.
- `bogey_worse_heatmap.png`: % of Bogey or Worse scores per hole/round.
- `requirements.txt`: Python dependencies.

## Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Run the script:**
   ```bash
   python scrape_pebble.py
   ```

## Methodology
- **Normalization:** `Deviation = (Hole_Round_Avg - Hole_All_Time_Avg) - (Course_Round_Avg - Global_Course_Avg)`. This highlights if a hole played uniquely easy/hard compared to the field's performance that day.
- **Wind Vectors:** Calculated using `Wind_Speed * cos(Wind_Dir - Hole_Dir)` for headwind.
- **Robustness:** Weather data ensures non-zero wind speeds based on airport observations during play hours.
