import time
import pandas as pd
import re
from playwright.sync_api import sync_playwright

# Configuration
YEARS_TO_SCRAPE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
OUTPUT_FILE = "genesis_history_scores.csv"

# PGA Tour Suffix
TOURNAMENT_ID_SUFFIX = "007"
TARGET_COURSE_KEYWORD = "Riviera"

# ESPN IDs for years where PGA Tour data is missing/empty
ESPN_IDS = {
    2018: "3748",
    2019: "401056515",
    2020: "401155423",
    2021: "401243001",
    2022: "401353237"
}

def scrape_pgatour_course_stats(page, year):
    """
    Scrapes course stats from PGA Tour site.
    Returns rows or empty list if failed/empty.
    """
    suffix = TOURNAMENT_ID_SUFFIX
    url = f"https://www.pgatour.com/tournaments/{year}/placeholder/R{year}{suffix}/course-stats"
    print(f"  PGA TOUR: Scraping {year} stats from {url}...")

    try:
        response = page.goto(url, timeout=30000, wait_until="domcontentloaded")
        if response.status == 404 or "schedule" in page.url:
            print(f"    Page not found/redirected.")
            return []

        # Check Course Name (Filter)
        course_name = "Unknown"
        try:
            potential_courses = page.locator(".css-pptzzz").all()
            for el in potential_courses:
                text = el.inner_text()
                if "Golf" in text or "Club" in text or "Links" in text or "Course" in text:
                    course_name = text
                    break
        except:
            pass

        if course_name == "Unknown":
            title = page.title()
            course_name = title.split(" - ")[0] if " - " in title else title

        print(f"    Detected Course: {course_name}")

        if TARGET_COURSE_KEYWORD.lower() not in course_name.lower():
             if TARGET_COURSE_KEYWORD in page.content():
                if "Riviera" not in course_name:
                    course_name = f"{course_name} (Riviera Country Club verified)"
             else:
                print(f"    WARNING: '{TARGET_COURSE_KEYWORD}' not found. Skipping.")
                return []

        # Check rounds
        round_nums = []
        try:
            buttons = page.locator("button", has_text=re.compile(r"Round \d")).all()
            seen = set()
            for btn in buttons:
                txt = btn.inner_text()
                r_match = re.search(r"Round (\d)", txt)
                if r_match:
                    r = int(r_match.group(1))
                    if r not in seen:
                        seen.add(r)
                        round_nums.append(r)
            round_nums.sort()
        except:
            pass

        rounds_to_scrape = [(r, True) for r in round_nums] if round_nums else [(0, False)]

        all_rows = []

        for r_num, needs_click in rounds_to_scrape:
            if needs_click:
                try:
                    page.locator(f"button:has-text('Round {r_num}')").first.click()
                    time.sleep(2)
                except:
                    continue

            # Check table
            try:
                page.wait_for_selector("table", timeout=5000)
            except:
                print("    Timeout waiting for table.")
                continue

            tables = page.locator("table").all()
            target_table = None
            for tbl in tables:
                try:
                    headers = tbl.locator("th").all_text_contents()
                    h_str = " ".join(headers).lower()
                    if "hole" in h_str and "par" in h_str:
                        target_table = tbl
                        break
                except:
                    continue

            if not target_table:
                continue

            rows = target_table.locator("tbody tr").all()

            for row in rows:
                cells = row.locator("td").all_text_contents()
                # PGA Tour Format: [Hole, Par, Yards, Avg, Rank, +/-, Eagles, Birdies, Pars, Bogeys, Dbl+]
                if len(cells) < 11: continue

                hole = cells[0].strip()
                if not hole.isdigit(): continue

                # Check for empty data (hyphens)
                if cells[6].strip() == "-" and cells[7].strip() == "-":
                    # Data is empty
                    return [] # Return empty to trigger fallback

                data_row = {
                    "Year": year,
                    "Source": "PGATOUR",
                    "Course_Name": course_name,
                    "Round": r_num if r_num > 0 else "Total",
                    "Hole": hole,
                    "Par": cells[1].strip(),
                    "Yards": cells[2].strip(),
                    "Eagles": cells[6].strip(),
                    "Birdies": cells[7].strip(),
                    "Pars": cells[8].strip(),
                    "Bogeys": cells[9].strip(),
                    "Double_Bogey_Plus": cells[10].strip()
                }
                all_rows.append(data_row)

        return all_rows

    except Exception as e:
        print(f"    Error scraping PGA Tour {year}: {e}")
        return []

def scrape_espn_course_stats(page, year):
    """
    Scrapes course stats from ESPN.
    """
    tid = ESPN_IDS.get(year)
    if not tid:
        print(f"    No ESPN ID for {year}.")
        return []

    url = f"https://www.espn.com/golf/leaderboard/_/tournamentId/{tid}"
    print(f"  ESPN: Scraping {year} (ID {tid}) from {url}...")

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        # Click Course Stats
        try:
            # Try exact text match first
            stats_btn = page.locator("text='Course Stats'").first
            if stats_btn.count() > 0:
                stats_btn.click()
            else:
                # Try partial match or links
                links = page.locator("a").all()
                clicked = False
                for link in links:
                    if "Course Stats" in link.inner_text():
                        link.click()
                        clicked = True
                        break
                if not clicked:
                     print("    'Course Stats' button not found.")
                     return []

            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except Exception as e:
            print(f"    Failed to click Course Stats: {e}")
            return []

        # Find Table
        try:
            page.wait_for_selector("table", timeout=5000)
            tables = page.locator("table").all()

            # Identify correct table
            target_table = None
            for tbl in tables:
                headers = tbl.locator("thead").inner_text().lower()
                if "hole" in headers and "par" in headers:
                    target_table = tbl
                    break

            if not target_table:
                print("    No stats table found.")
                return []

            rows = target_table.locator("tbody tr").all()
            all_rows = []

            for row in rows:
                cells = row.locator("td").all_text_contents()
                # ESPN Format: HOLE, PAR, YARDS, AVG SCORE, EAGLES, BIRDIES, PARS, BOGEYS, DOUBLES, OTHER, +/- AVG
                # Indices: Hole=0, Par=1, Yards=2, Eagles=4, Birdies=5, Pars=6, Bogeys=7, Doubles=8, Other=9

                if len(cells) < 10: continue

                hole = cells[0].strip()
                if not hole.isdigit(): continue

                # Combine Doubles and Other for Double+
                dbl = 0
                other = 0
                try:
                    if cells[8].strip().isdigit(): dbl = int(cells[8].strip())
                    if cells[9].strip().isdigit(): other = int(cells[9].strip())
                except:
                    pass
                dbl_plus = dbl + other

                data_row = {
                    "Year": year,
                    "Source": "ESPN",
                    "Course_Name": "Riviera Country Club", # ESPN usually is correct
                    "Round": "Total", # ESPN usually shows Tournament Total on this view
                    "Hole": hole,
                    "Par": cells[1].strip(),
                    "Yards": cells[2].strip(),
                    "Eagles": cells[4].strip(),
                    "Birdies": cells[5].strip(),
                    "Pars": cells[6].strip(),
                    "Bogeys": cells[7].strip(),
                    "Double_Bogey_Plus": str(dbl_plus)
                }
                all_rows.append(data_row)

            return all_rows

        except Exception as e:
            print(f"    Error parsing ESPN table: {e}")
            return []

    except Exception as e:
        print(f"    Error scraping ESPN {year}: {e}")
        return []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use user agent
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        page = context.new_page()

        all_data = []

        for year in YEARS_TO_SCRAPE:
            # Try PGA Tour first
            data = scrape_pgatour_course_stats(page, year)

            # If PGA Tour data is empty or missing, try ESPN
            if not data:
                print(f"    PGA Tour data missing/empty for {year}. Trying ESPN...")
                data = scrape_espn_course_stats(page, year)

            if data:
                print(f"    Collected {len(data)} rows for {year}.")
                all_data.extend(data)
            else:
                print(f"    No data collected for {year}.")

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
