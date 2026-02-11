import asyncio
import json
import csv
import traceback
from playwright.async_api import async_playwright

class CourseStatsScraper:
    def __init__(self, years, tournament_slug, tournament_id_suffix, target_course_name):
        self.years = years
        self.tournament_slug = tournament_slug
        self.tournament_id_suffix = tournament_id_suffix
        self.target_course_name = target_course_name
        self.results = []

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            for year in self.years:
                tournament_id = f"R{year}{self.tournament_id_suffix}"
                url = f"https://www.pgatour.com/tournaments/{year}/{self.tournament_slug}/{tournament_id}/course-stats"
                print(f"Scraping {year} - {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                    # Extract __NEXT_DATA__
                    try:
                        next_data_html = await page.inner_html("#__NEXT_DATA__", timeout=15000)
                        data = json.loads(next_data_html)
                        self.process_data(data, year)
                    except Exception as e:
                        print(f"Error extracting data for {year}: {e}")

                except Exception as e:
                    print(f"Error loading page for {year}: {e}")

            await browser.close()

    def process_data(self, data, year):
        try:
            queries = data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])

            course_data_found = False
            for q in queries:
                if 'state' in q and 'data' in q['state'] and 'courses' in q['state']['data']:
                    courses = q['state']['data']['courses']

                    for course in courses:
                        course_name = course.get('courseName', '')
                        if self.target_course_name.lower() not in course_name.lower():
                            continue

                        course_data_found = True
                        round_stats = course.get('roundHoleStats', [])

                        for round_stat in round_stats:
                            round_num = round_stat.get('roundNum')
                            # Skip 'None' round (Total)
                            if not round_num:
                                continue

                            hole_stats = round_stat.get('holeStats', [])
                            for hole in hole_stats:
                                hole_num = hole.get('courseHoleNum')
                                if not hole_num:
                                    continue

                                pin_green = hole.get('pinGreen', {})
                                # Coordinates
                                pin_x_norm = pin_green.get('leftToRightCoords', {}).get('x', -1)
                                pin_y_norm = pin_green.get('bottomToTopCoords', {}).get('y', -1) # Use bottomToTop y for depth

                                # Scoring Data
                                # Sometimes scoring data is strings, sometimes ints
                                try:
                                    avg_score = float(hole.get('scoringAverage', 0))
                                except: avg_score = 0

                                row = {
                                    'Year': year,
                                    'Course': course_name,
                                    'Round': round_num,
                                    'Hole': hole_num,
                                    'Par': hole.get('parValue'),
                                    'Avg_Score': avg_score,
                                    'Eagles': hole.get('eagles', 0),
                                    'Birdies': hole.get('birdies', 0),
                                    'Pars': hole.get('pars', 0),
                                    'Bogeys': hole.get('bogeys', 0),
                                    'Doubles': hole.get('doubleBogey', 0), # JSON uses doubleBogey
                                    'Pin_X_Normalized': pin_x_norm,
                                    'Pin_Y_Normalized': pin_y_norm
                                }
                                self.results.append(row)

            if not course_data_found:
                print(f"No data found for course '{self.target_course_name}' in {year}")

        except Exception as e:
            print(f"Error processing data for {year}: {e}")
            traceback.print_exc()

    def save_csv(self, filename):
        if not self.results:
            print("No data to save.")
            return

        keys = self.results[0].keys()
        with open(filename, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(self.results)
        print(f"Data saved to {filename}")

async def main():
    # Pebble Beach Config
    print("--- Scraping Pebble Beach ---")
    pebble_scraper = CourseStatsScraper(
        years=[2021, 2022, 2023, 2024, 2025],
        tournament_slug="att-pebble-beach-pro-am",
        tournament_id_suffix="005",
        target_course_name="Pebble Beach Golf Links"
    )
    await pebble_scraper.scrape()
    pebble_scraper.save_csv("pebble_beach_data_combined.csv")

    # Augusta Config
    print("\n--- Scraping Augusta National ---")
    augusta_scraper = CourseStatsScraper(
        years=[2021, 2022, 2023, 2024],
        tournament_slug="masters-tournament",
        tournament_id_suffix="014",
        target_course_name="Augusta National Golf Club"
    )
    await augusta_scraper.scrape()
    augusta_scraper.save_csv("masters_scoring_data.csv")

if __name__ == "__main__":
    asyncio.run(main())
