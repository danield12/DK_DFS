# AT&T Pebble Beach Pro-Am Scoring & Weather Analysis

This project scrapes **round-level** hole-by-hole scoring data for the **Pebble Beach Golf Links** course from the **AT&T Pebble Beach Pro-Am** tournament (2023, 2024, 2025) and integrates historical weather data to analyze the impact of conditions on scoring.

## Data Source
- **Scoring Data:** Scraped from [PGATour.com](https://www.pgatour.com) using `playwright` to interact with the Next.js application, select the correct course, and iterate through each round's data table.
- **Weather Data:** Manually researched and integrated for each round (Wind Speed, Temperature, Condition Index).

## Files
- `scrape_pebble.py`: Main script to scrape data, merge weather, save CSV, and generate visualizations.
- `pebble_beach_scoring_history.csv`: Aggregated scoring data including weather metrics.
  - Columns: `Year`, `Round`, `Hole`, `Par`, `Avg_Score`, `Eagles`, `Birdies`, `Pars`, `Bogeys`, `Doubles`, `Wind_mph`, `Temp_F`, `Condition_Index`, `Rel_Score`
- `scoring_fluctuation_heatmap.png`: Heatmap visualizing the fluctuation of average scores relative to par across rounds.
- `hole_wind_impact.png`: Heatmap showing average score relative to par for each hole under Low/Medium/High wind conditions.
- `wind_vs_score.png`: Scatter plot with regression line showing the impact of Wind Speed on scoring.
- `temp_vs_score.png`: Scatter plot with regression line showing the impact of Temperature on scoring.
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

3. **Output:**
   - The script will generate the CSV and PNG files listed above.
   - It will also print a correlation matrix to the console.

## Methodology
- **Condition Index:** A simple metric (1=Dry, 2=Damp, 3=Wet) used to categorize course softness based on historical weather reports.
- **Course Verification:** The script explicitly verifies "Pebble Beach Golf Links" is the active course to avoid data contamination from Spyglass Hill or Monterey Peninsula CC.
