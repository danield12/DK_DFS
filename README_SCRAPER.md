# PGA Tour Hole Location Scraper

This script scrapes hole location data from the PGA Tour website for a specified tournament and years.

## Requirements

- Python 3.7+
- `playwright`
- `playwright` browser binaries

Install dependencies:
```bash
pip install playwright
playwright install chromium
```

## Usage

Run the script:
```bash
python scrape_hole_locations.py
```

This will generate a `hole_locations.csv` file containing the scraped data.

## Configuration

To change the tournament or years, edit the variables at the bottom of `scrape_hole_locations.py`:

```python
if __name__ == "__main__":
    # EDITABLE CONFIGURATION
    YEARS = [2023, 2024, 2025]
    TOURNAMENT_SLUG = "att-pebble-beach-pro-am"  # URL slug for the tournament
    TOURNAMENT_ID_SUFFIX = "005"                 # Suffix for the tournament ID (e.g., R2024005 -> 005)
```

## Data Notes

- **Hole Depth**: This information is not directly available in the scraped JSON data and is marked as "N/A".
- **Pin Locations**: The pin locations are provided as **normalized coordinates** (0.0 to 1.0).
  - `Pin Location From Front (Normalized)`: 0.0 is the front, 1.0 is the back.
  - `Pin Location From Side (Normalized)`: 0.0 is the left edge, 1.0 is the right edge.
- **Side**: Derived from the X coordinate (Left if < 0.5, Right if >= 0.5).

## Troubleshooting

If the script fails to find data:
1. Check if the URL structure for the tournament matches the expected format: `https://www.pgatour.com/tournaments/{year}/{slug}/R{year}{suffix}/course-stats`.
2. Increase the timeout in `page.goto()` if the page loads slowly.
3. Ensure `playwright` is installed correctly.
