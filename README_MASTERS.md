# Masters Scraping & Analysis

This project scrapes historical scoring data for The Masters (2021-2024) from PGATour.com and analyzes the impact of wind and pin locations.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install pandas playwright beautifulsoup4 matplotlib seaborn numpy
    playwright install
    ```

2.  **Pin Locations**:
    The analysis requires a file named `masters_pin_locations.csv`.
    A template has been provided with the columns: `Year`, `Round`, `Hole`, `Pin_Location`.

    **Please fill this file with the actual pin locations** (e.g., "Front Left", "Back Right", "Zone 1", etc.) for each hole and round for the years 2021-2024.
    If this file is missing or incomplete, the script will skip the pin location grouping analysis but will still perform the weather analysis.

## Running the Script

Run the script using Python:

```bash
python scrape_masters.py
```

## Output

-   `masters_scoring_history.csv`: The scraped scoring data merged with weather.
-   `masters_pin_impact.csv`: The analysis of Birdie/Bogey magnitude increase per pin location (if pin data is provided).
-   `*.png`: Visualizations of the data.
