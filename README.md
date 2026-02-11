# AT&T Pebble Beach Pro-Am Scoring History

This project scrapes **round-level** hole-by-hole scoring data for the **Pebble Beach Golf Links** course from the **AT&T Pebble Beach Pro-Am** tournament (2023, 2024, 2025).

## Data Source
The data is scraped from [PGATour.com](https://www.pgatour.com) using `playwright` to interact with the Next.js application, select the correct course, and iterate through each round's data table.

## Files
- `scrape_pebble.py`: Main script to scrape data, save CSV, and generate visualization.
- `pebble_beach_scoring_history.csv`: Aggregated scoring data with `Year`, `Round`, `Hole`, and scoring metrics.
- `scoring_fluctuation_heatmap.png`: Heatmap visualizing the fluctuation of average scores relative to par across rounds and years.
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
   - `pebble_beach_scoring_history.csv` (Columns: Year, Round, Hole, Par, Avg_Score, Eagles, Birdies, Pars, Bogeys, Doubles)
   - `scoring_fluctuation_heatmap.png`

## Key Features
- **Round-Level Granularity:** Captures data for each round (R1, R2, R3, R4) independently.
- **Course Verification:** Ensures data is for "Pebble Beach Golf Links" even if other courses are played (e.g., Spyglass Hill).
- **Handling Shortened Events:** Automatically detects available rounds (e.g., handles the 54-hole finish in 2024).
