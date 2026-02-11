import json
import csv
from playwright.sync_api import sync_playwright

class HoleLocationScraper:
    def __init__(self, years, tournament_name_slug, tournament_id_suffix):
        """
        Initialize the scraper.
        :param years: List of years to scrape (e.g., [2023, 2024, 2025])
        :param tournament_name_slug: The URL slug for the tournament (e.g., 'att-pebble-beach-pro-am')
        :param tournament_id_suffix: The suffix for the tournament ID (e.g., '005') which combined with Year forms the ID (e.g., R2024005)
        """
        self.years = years
        self.tournament_name_slug = tournament_name_slug
        self.tournament_id_suffix = tournament_id_suffix
        self.results = []

    def scrape(self):
        with sync_playwright() as p:
            # Use a realistic user agent to avoid bot detection
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = context.new_page()

            for year in self.years:
                tournament_id = f"R{year}{self.tournament_id_suffix}"
                url = f"https://www.pgatour.com/tournaments/{year}/{self.tournament_name_slug}/{tournament_id}/course-stats"
                print(f"Scraping {year} - {url}")

                try:
                    page.goto(url, timeout=60000)
                    page.wait_for_timeout(5000) # Wait for dynamic content

                    # Extract __NEXT_DATA__
                    next_data_html = page.inner_html("#__NEXT_DATA__")
                    if next_data_html:
                        data = json.loads(next_data_html)
                        self.process_data(data, year)
                    else:
                        print(f"Could not find __NEXT_DATA__ for {year}")
                except Exception as e:
                    print(f"Error scraping {year}: {e}")

            browser.close()

    def process_data(self, data, year):
        try:
            queries = data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])

            # Find the query containing course stats
            courses = None
            for q in queries:
                if 'state' in q and 'data' in q['state'] and 'courses' in q['state']['data']:
                    potential_courses = q['state']['data']['courses']
                    if potential_courses and 'roundHoleStats' in potential_courses[0]:
                        courses = potential_courses
                        break

            if not courses:
                print(f"No course data found for {year}")
                return

            for course in courses:
                course_name = course.get('courseName', 'Unknown Course')
                round_stats = course.get('roundHoleStats', [])

                for round_stat in round_stats:
                    round_num = round_stat.get('roundNum')
                    if not round_num:
                        continue

                    hole_stats = round_stat.get('holeStats', [])
                    for hole in hole_stats:
                        hole_num = hole.get('courseHoleNum')
                        if not hole_num:
                            continue

                        pin_green = hole.get('pinGreen', {})

                        # Extract coordinates (normalized 0.0-1.0)
                        # bottomToTopCoords.y is likely distance from front (0 is front, 1 is back)
                        # leftToRightCoords.x is likely distance from left (0 is left, 1 is right)

                        pin_y_normalized = pin_green.get('bottomToTopCoords', {}).get('y', -1)
                        pin_x_normalized = pin_green.get('leftToRightCoords', {}).get('x', -1)

                        side = "Unknown"
                        if pin_x_normalized != -1:
                            if pin_x_normalized < 0.5:
                                side = "Left"
                            else:
                                side = "Right"

                        # The user asked for "Hole Depth", "Pin Location from the Front", "Pin Location from the Side"
                        # Since we only have normalized coordinates, we provide those.
                        # "Hole Depth" is not available in the JSON directly.

                        self.results.append({
                            'Year': year,
                            'Course': course_name,
                            'Round': round_num,
                            'Hole': hole_num,
                            'Hole Depth': 'N/A', # Not available in JSON
                            'Pin Location From Front (Normalized)': pin_y_normalized,
                            'Pin Location From Side (Normalized)': pin_x_normalized,
                            'Side': side
                        })

        except Exception as e:
            print(f"Error processing data for {year}: {e}")

    def save_csv(self, filename="hole_locations.csv"):
        if not self.results:
            print("No data to save.")
            return

        keys = self.results[0].keys()
        with open(filename, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(self.results)
        print(f"Data saved to {filename}")

if __name__ == "__main__":
    # EDITABLE CONFIGURATION
    YEARS = [2023, 2024, 2025]
    TOURNAMENT_SLUG = "att-pebble-beach-pro-am"
    TOURNAMENT_ID_SUFFIX = "005"

    scraper = HoleLocationScraper(YEARS, TOURNAMENT_SLUG, TOURNAMENT_ID_SUFFIX)
    scraper.scrape()
    scraper.save_csv()
