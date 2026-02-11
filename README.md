# AT&T Pebble Beach Pro-Am Scoring & Weather Analysis

This project scrapes **round-level** hole-by-hole scoring data for the **Pebble Beach Golf Links** course from the **AT&T Pebble Beach Pro-Am** tournament (2023, 2024, 2025) and integrates historical weather data (including Wind Direction) to analyze the impact of conditions on scoring.

## Data Source
- **Scoring Data:** Scraped from [PGATour.com](https://www.pgatour.com) using `playwright` to interact with the Next.js application, select the correct course, and iterate through each round's data table.
- **Weather Data:** Manually researched and integrated for each round (Wind Speed, Temperature, Condition Index, Wind Direction).
- **Course Data:** Estimated Hole Azimuths (Tee-to-Green direction) for vector analysis.

## Files
- `scrape_pebble.py`: Main script to scrape data, merge weather, calculate wind vectors, and generate visualizations.
- `pebble_beach_scoring_history.csv`: Aggregated scoring data including weather metrics.
  - New Columns: `Wind_Dir_Deg`, `Hole_Azimuth`, `Headwind_Comp` (Positive = Headwind, Negative = Tailwind), `Crosswind_Comp` (Absolute lateral wind).
- `scoring_fluctuation_heatmap.png`: Heatmap visualizing the fluctuation of average scores relative to par across rounds.
- `headwind_impact.png`: Scatter plot showing impact of Headwind/Tailwind on scoring.
- `crosswind_impact.png`: Scatter plot showing impact of Crosswind on scoring.
- `wind_vs_score.png`: Scatter plot showing impact of Total Wind Speed on scoring.
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
- **Vector Analysis:** Wind is decomposed into Headwind (Parallel to hole) and Crosswind (Perpendicular to hole) components using the estimated azimuth of each hole.
- **Condition Index:** A simple metric (1=Dry, 2=Damp, 3=Wet) used to categorize course softness based on historical weather reports.
