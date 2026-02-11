# Pin Difficulty Analysis & Green Heat-Mapping

This project analyzes the impact of pin locations on scoring difficulty, isolating it from weather and field conditions.

## Scripts

### 1. `scrape_hole_locations_async.py`
Scrapes scoring data and pin locations (digital coordinates) from the PGA Tour website.
*   **Usage**: `python scrape_hole_locations_async.py`
*   **Outputs**:
    *   `pebble_beach_data_combined.csv` (Pebble Beach scoring + pin coordinates)
    *   `masters_scoring_data.csv` (Augusta scoring data)

### 2. `analyze_pin_difficulty.py`
Performs the core analysis:
*   **Zoning**: Maps pin coordinates (Pebble) or descriptions (Augusta) to a 3x3 Grid (Back-Left, Middle-Center, Front-Right, etc.).
*   **Isolation**: Calculates "Pin Difficulty" by subtracting the "Hole Baseline" and "Field Adjustment" (weather/course condition bias) from the actual score.
*   **Impact Metrics**: Calculates how much a specific zone increases/decreases Birdie and Bogey probabilities.
*   **Usage**: `python analyze_pin_difficulty.py`
*   **Outputs**:
    *   `pin_difficulty_cheat_sheet.csv`: A table classifying pins as "Green Light", "Sucker Pin", or "Neutral/Hard" for each hole/zone.
    *   `pebble_hole_{N}_analysis.png`: Heatmaps for each hole showing Pin Difficulty and Birdie Impact per zone.

## Data Files

*   `pebble_beach_data_combined.csv`: Scraped data for Pebble Beach (2023-2025).
*   `masters_scoring_data.csv`: Scraped data for Augusta National (2023-2024).
*   `masters_pin_locations.csv`: (Partial) Manual pin location data for Augusta.

## Methodology

**Pin Difficulty Formula**:
$$ \text{Pin Difficulty} = (\text{Hole Avg on Day } D) - (\text{Hole Baseline}) - (\text{Field Adjustment on Day } D) $$

**Zoning**:
For Pebble Beach, digital coordinates are used. Since the coordinates are relative to the overhead image, the script dynamically calculates the "Green Box" (min/max observed pin locations per hole) and divides it into a 3x3 grid.
