import time
import pandas as pd
import re
from playwright.sync_api import sync_playwright

# Configuration
YEARS_TO_SCRAPE = [2020, 2021, 2022, 2023, 2024]
OUTPUT_FILE = "pga_historical_scores.csv"
SCHEDULE_URL = "https://www.pgatour.com/schedule/2025"

def get_tournaments_2025(page):
    """
    Scrapes the 2025 schedule to get a list of tournament IDs and names.
    Returns a list of dicts: {'name': str, 'id': str, 'suffix': str}
    """
    print(f"Scraping schedule from {SCHEDULE_URL}...")
    page.goto(SCHEDULE_URL, timeout=60000, wait_until="domcontentloaded")

    # Extract links with pattern /tournaments/{year}/{slug}/{id}
    # We look for links that contain '/tournaments/'
    # The ID format is usually R{Year}{Suffix}

    links = page.locator("a[href*='/tournaments/']").all()

    tournaments = {}

    for link in links:
        href = link.get_attribute("href")
        if not href:
            continue

        # Regex to match /tournaments/2025/slug/R2025xxx
        # The ID format is usually R{Year}{Suffix} where Suffix is 3 digits.
        # e.g. R2025016 -> Year 2025, Suffix 016
        match = re.search(r"/tournaments/(\d{4})/([^/]+)/(R(\d{4})(\d{3}))", href)
        if match:
            url_year, slug, full_id, id_year, suffix = match.groups()

            # Use suffix as unique key
            if suffix not in tournaments:
                # Get tournament name from link text or just use slug
                # Link text might be messy (e.g. "Leaderboard", "Course Stats")
                # We can try to get the text of the tournament name element if we can identify it.
                # But slug is a good proxy.
                tournaments[suffix] = {
                    'name': slug.replace("-", " ").title(),
                    'slug': slug,
                    'suffix': suffix,
                    'example_id': full_id
                }
                print(f"Found tournament: {slug} (ID: {full_id}, Suffix: {suffix})")

    print(f"Found {len(tournaments)} unique tournaments.")
    return list(tournaments.values())

def scrape_course_stats(page, tournament, year):
    """
    Scrapes course stats for a given tournament suffix and year.
    Returns a list of dicts (rows).
    """
    suffix = tournament['suffix']
    # Construct URL: https://www.pgatour.com/tournaments/{year}/placeholder/R{year}{suffix}/course-stats
    # Using 'placeholder' as slug because it's ignored if ID is correct.
    url = f"https://www.pgatour.com/tournaments/{year}/placeholder/R{year}{suffix}/course-stats"

    print(f"  Scraping {year} stats from {url}...")

    try:
        response = page.goto(url, timeout=30000, wait_until="domcontentloaded")

        # Check if 404 or redirected to somewhere else (e.g. homepage or schedule)
        if response.status == 404:
            print(f"    Page not found (404). Skipping.")
            return []

        # Check if "Course Stats" is present
        # Sometimes it redirects to Leaderboard if stats aren't available
        if "Course Stats" not in page.title() and "Course Stats" not in page.content():
            print(f"    'Course Stats' not found in title/content. Skipping.")
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

        # Check for multiple courses (heuristic)
        page_text = page.content()
        if "Spyglass Hill" in page_text and "Pebble Beach" in page_text:
             course_name += " (Multiple Courses)"
        elif "North Course" in page_text and "South Course" in page_text:
             course_name += " (Multiple Courses)"

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
                    "Tournament_Name": tournament['name'],
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

        # Step 1: Get Tournaments
        tournaments = get_tournaments_2025(page)

        # Limit for testing?
        # tournaments = tournaments[:1]

        all_data = []

        # Step 2: Loop Tournaments and Years
        for i, tourney in enumerate(tournaments):
            print(f"[{i+1}/{len(tournaments)}] Processing {tourney['name']} (Suffix: {tourney['suffix']})")

            for year in YEARS_TO_SCRAPE:
                data = scrape_course_stats(page, tourney, year)
                all_data.extend(data)

            # Optional: Save partial progress
            if i % 5 == 0:
                pd.DataFrame(all_data).to_csv(OUTPUT_FILE, index=False)

        browser.close()

        # Save Final CSV
        df = pd.DataFrame(all_data)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"Done! Saved {len(df)} rows to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
