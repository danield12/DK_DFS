# AT&T Pebble Beach Pro-Am Scoring History

This project scrapes hole-by-hole scoring data for the **Pebble Beach Golf Links** course from the **AT&T Pebble Beach Pro-Am** tournament (2023, 2024, 2025).

## Data Source
The data is scraped from [PGATour.com](https://www.pgatour.com) using `playwright` to bypass CloudFront protection and render the dynamic Next.js application content.

## Files
- `scrape_pebble.py`: The main script to scrape data, save CSV, and generate heatmap.
- `pebble_beach_scoring_history.csv`: Aggregated scoring data for 3 years.
- `scoring_heatmap.png`: Heatmap visualization of scoring distribution (percentage of Eagles, Birdies, Pars, Bogeys, Doubles).
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
   - `pebble_beach_scoring_history.csv`
   - `scoring_heatmap.png`

## Notes
- The script automatically handles the default course selection (Pebble Beach Golf Links).
- It verifies the page content before scraping.
- The 2024 data reflects the shortened 54-hole tournament as aggregated by the official stats page.
