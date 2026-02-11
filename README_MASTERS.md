# Masters Scraping & Analysis

This project scrapes historical scoring data for The Masters (2020-2024) from PGATour.com and analyzes the impact of wind and pin locations.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install pandas playwright beautifulsoup4 matplotlib seaborn numpy
    playwright install
    ```

2.  **Pin Locations**:
    The analysis requires a file named `masters_pin_locations.csv`.
    A template has been provided with the columns: `Year`, `Round`, `Hole`, `Pin_Location`.

    **Important**: Please provide specific descriptions for the pin locations. Do not assume all pins in the same quadrant are equal.
    - **Bad**: "Front Left"
    - **Good**: "Front Left - Bowl", "Front Left - Ridge", "Back Right - Sunday Pin"

    The script will group performance stats by these unique string identifiers per hole.

## Running the Script

Run the script using Python:

```bash
python scrape_masters.py
```

## Output

-   `masters_scoring_history.csv`: The scraped scoring data merged with weather.
-   `masters_pin_impact.csv`: The analysis of Birdie/Bogey magnitude increase per pin location (if pin data is provided).
-   `*.png`: Visualizations of the data.
