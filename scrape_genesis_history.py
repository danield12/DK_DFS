import time
import pandas as pd
import re
from playwright.sync_api import sync_playwright

# Configuration
YEARS_TO_SCRAPE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
OUTPUT_FILE = "genesis_history_scores.csv"
TOURNAMENT_ID_SUFFIX = "007" # Genesis Invitational / Genesis Open
TARGET_COURSE_KEYWORD = "Riviera"

def scrape_course_stats(page, year):
    """
    Scrapes course stats for Genesis (007) for a given year.
    Returns a list of dicts (rows).
    """
    suffix = TOURNAMENT_ID_SUFFIX
    # Construct URL: https://www.pgatour.com/tournaments/{year}/placeholder/R{year}{suffix}/course-stats
    # Note: PGA Tour URLs often use a slug, but 'placeholder' or 'the-genesis-invitational' might work.
    # For older years (2018), the slug might be 'genesis-open'.
    # But usually the ID is the source of truth.
    # Let's try 'placeholder' first, if that fails (redirects), we might need the correct slug.
    # However, based on previous tests, 403 might indicate invalid structure or protection.

    url = f"https://www.pgatour.com/tournaments/{year}/placeholder/R{year}{suffix}/course-stats"
    print(f"  Scraping {year} stats from {url}...")

    try:
        response = page.goto(url, timeout=30000, wait_until="domcontentloaded")

        # Check if 404
        if response.status == 404:
            print(f"    Page not found (404). Skipping.")
            return []

        # Check if redirected to schedule or homepage
        if "schedule" in page.url or "pgatour.com" == page.url.rstrip("/"):
            print(f"    Redirected to {page.url}. Skipping.")
            return []

        # Extract Course Name
        course_name = "Unknown"

        # Strategy 1: Look for specific class observed in inspection (.css-pptzzz)
        try:
            # Look for elements with this class that contain "Golf" or "Club" or "Links"
            potential_courses = page.locator(".css-pptzzz").all()
            for el in potential_courses:
                text = el.inner_text()
                if "Golf" in text or "Club" in text or "Links" in text or "Course" in text:
                    course_name = text
                    break
        except:
            pass

        # Strategy 2: Fallback to Title
        if course_name == "Unknown":
            title = page.title()
            # Remove "Golf Leaderboard - PGA TOUR - Course Stats"
            course_name = title.split(" - ")[0] if " - " in title else title

        print(f"    Detected Course: {course_name}")

        # Strict Filter: Must contain "Riviera"
        if TARGET_COURSE_KEYWORD.lower() not in course_name.lower():
            # Sometimes the course name is just "The Genesis Invitational" in the title if the element wasn't found.
            # But the page content definitely mentions Riviera.
            # Let's check page content as a backup.
            if TARGET_COURSE_KEYWORD in page.content():
                print(f"    '{TARGET_COURSE_KEYWORD}' found in page content. Proceeding (Course Name might be generic).")
                # Update course name if generic
                if "Riviera" not in course_name:
                    course_name = f"{course_name} (Riviera Country Club verified)"
            else:
                print(f"    WARNING: '{TARGET_COURSE_KEYWORD}' not found in Course Name or Page Content. Skipping.")
                return []

        # Iterate Rounds
        # Find unique round numbers first
        round_nums = []
        try:
            buttons = page.locator("button", has_text=re.compile(r"Round \d")).all()
            seen_rounds = set()
            for btn in buttons:
                txt = btn.inner_text()
                r_match = re.search(r"Round (\d)", txt)
                if r_match:
                    r_num = int(r_match.group(1))
                    if r_num not in seen_rounds:
                        seen_rounds.add(r_num)
                        round_nums.append(r_num)
            round_nums.sort()
        except:
            pass

        rounds_to_scrape = []
        if round_nums:
            print(f"    Found {len(round_nums)} rounds: {round_nums}")
            # Use tuple (round_number, needs_click)
            rounds_to_scrape = [(r, True) for r in round_nums]
        else:
            print(f"    No round buttons found. Assuming single table (Total/Round 1).")
            rounds_to_scrape = [(0, False)]

        all_rows = []

        for r_num, needs_click in rounds_to_scrape:
            if needs_click:
                print(f"    Clicking Round {r_num}...")
                # Re-query button to avoid stale element
                try:
                    # Click the button with exact text "Round X" if possible, or containing it
                    page.locator(f"button:has-text('Round {r_num}')").first.click()
                    time.sleep(2) # Wait for update
                except Exception as e:
                    print(f"    Failed to click Round {r_num}: {e}")
                    continue

            # Scrape Table
            # Wait for table to appear
            try:
                page.wait_for_selector("table", timeout=5000)
            except:
                print("    Timeout waiting for table.")
                continue

            # Look for table with headers: Hole, Par, etc.
            tables = page.locator("table").all()

            target_table = None
            for tbl in tables:
                # Check headers
                try:
                    headers = tbl.locator("th").all_text_contents()
                    # Flatten/join headers to check presence
                    header_str = " ".join(headers).lower()
                    if "hole" in header_str and "par" in header_str:
                        target_table = tbl
                        break
                except:
                    continue

            if not target_table:
                print("    No stats table found.")
                continue

            # Extract rows
            # Rows are in tbody -> tr
            rows = target_table.locator("tbody tr").all()

            for row in rows:
                cells = row.locator("td").all_text_contents()
                # Expected columns: Hole, Par, Yards, Avg, Rank, +/-, Eagles, Birdies, Pars, Bogeys, Dbl+
                # Count: 11
                if len(cells) < 11:
                    continue

                # Clean up data
                hole = cells[0].strip()
                par = cells[1].strip()
                yards = cells[2].strip()
                # avg = cells[3]
                # rank = cells[4]
                # plus_minus = cells[5]
                eagles = cells[6].strip()
                birdies = cells[7].strip()
                pars = cells[8].strip()
                bogeys = cells[9].strip()
                dbl_plus = cells[10].strip()

                if not hole.isdigit():
                    continue # Skip summary rows like "Out", "In", "Total"

                data_row = {
                    "Year": year,
                    "Tournament_Suffix": suffix,
                    "Course_Name": course_name,
                    "Round": r_num if r_num > 0 else "Total",
                    "Hole": hole,
                    "Par": par,
                    "Yards": yards,
                    "Eagles": eagles,
                    "Birdies": birdies,
                    "Pars": pars,
                    "Bogeys": bogeys,
                    "Double_Bogey_Plus": dbl_plus
                }
                all_rows.append(data_row)

        return all_rows

    except Exception as e:
        print(f"    Error scraping {year}: {e}")
        return []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Random user agent to avoid blocking
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        page = context.new_page()

        all_data = []

        for year in YEARS_TO_SCRAPE:
            data = scrape_course_stats(page, year)
            if data:
                all_data.extend(data)
            else:
                print(f"No data scraped for {year}.")

        browser.close()

        # Save Final CSV
        if all_data:
            df = pd.DataFrame(all_data)
            df.to_csv(OUTPUT_FILE, index=False)
            print(f"Done! Saved {len(df)} rows to {OUTPUT_FILE}")
        else:
            print("No data collected.")

if __name__ == "__main__":
    main()
