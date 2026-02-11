import pdfplumber
import pandas as pd
import argparse
import os
import re

def extract_hole_locations(pdf_path, override_course=None, override_year=None, override_round=None):
    """
    Extracts hole location data from a PDF file.
    """
    data = []
    course_name = override_course if override_course else "Unknown Course"
    round_num = override_round if override_round else "Unknown"
    year = override_year if override_year else "Unknown"

    # Try to extract year from filename first if not overridden
    if not override_year:
        filename = os.path.basename(pdf_path)
        year_match = re.search(r'(20\d{2})', filename)
        if year_match:
            year = year_match.group(1)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            tables = page.extract_tables()

            # Attempt to find metadata in text if not already found
            if text:
                lines = text.split('\n')
                for line in lines:
                    # Look for Round information if not overridden
                    if not override_round and "Round" in line and round_num == "Unknown":
                        round_match = re.search(r'Round\s+(\d+)', line, re.IGNORECASE)
                        if round_match:
                            round_num = round_match.group(1)

                    # Look for Year if not overridden and not in filename
                    if not override_year and year == "Unknown":
                        year_match_text = re.search(r'(20\d{2})', line)
                        if year_match_text:
                            year = year_match_text.group(1)

                    # Attempt to find course name (heuristic: often at the top, or contains "Course")
                    # This is tricky without knowing the format.
                    # For now, we might leave it or use the first non-empty line as a candidate if it doesn't look like a header

            for table in tables:
                # Check if this table looks like hole locations
                # We expect columns like Hole, Front, Side, Depth
                # Headers are usually the first row, but sometimes not.

                df = pd.DataFrame(table)

                # Normalize headers: find the row that contains "Hole"
                header_row_idx = -1
                for idx, row in df.iterrows():
                    row_str = " ".join([str(x) for x in row if x]).lower()
                    if "hole" in row_str and ("front" in row_str or "pace" in row_str or "depth" in row_str):
                        header_row_idx = idx
                        break

                if header_row_idx != -1:
                    # Set header
                    headers = df.iloc[header_row_idx]
                    df = df.iloc[header_row_idx + 1:]
                    df.columns = headers

                    # Normalize column names
                    df.columns = [str(col).strip() for col in df.columns]

                    # Identify columns (case-insensitive)
                    hole_col = next((c for c in df.columns if "hole" in str(c).lower()), None)
                    front_col = next((c for c in df.columns if "front" in str(c).lower() or "pace" in str(c).lower()), None) # Sometimes called Pace?
                    side_col = next((c for c in df.columns if "side" in str(c).lower()), None)
                    depth_col = next((c for c in df.columns if "depth" in str(c).lower()), None)

                    if hole_col and (front_col or side_col or depth_col):
                        for _, row in df.iterrows():
                            hole_val = row[hole_col]
                            if not hole_val or not str(hole_val).isdigit():
                                continue

                            entry = {
                                "Year": year,
                                "Course": course_name, # Placeholder
                                "Round": round_num,
                                "Hole": hole_val,
                                "Distance from Front": row[front_col] if front_col else "",
                                "Distance From Side": "", # To be split
                                "Side": "", # To be split
                                "Green Depth": row[depth_col] if depth_col else ""
                            }

                            # Parse Side column which often contains "5L" or "5 L" or "5 Right"
                            if side_col:
                                raw_side_val = row[side_col]
                                if raw_side_val and str(raw_side_val).strip() and str(raw_side_val).lower() != "none":
                                    side_val = str(raw_side_val).strip()
                                    # Logic to split distance and side
                                    # Common formats: "5 R", "5R", "5 Right"
                                    side_match = re.search(r'(\d+)\s*([A-Za-z]+)', side_val)
                                    if side_match:
                                        entry["Distance From Side"] = side_match.group(1)
                                        side_dir = side_match.group(2).lower()
                                        if 'r' in side_dir:
                                            entry["Side"] = "Right"
                                        elif 'l' in side_dir:
                                            entry["Side"] = "Left"
                                        else:
                                            entry["Side"] = side_dir.capitalize()
                                    else:
                                        # Maybe just a number?
                                        entry["Distance From Side"] = side_val

                            data.append(entry)

    return data

def main():
    parser = argparse.ArgumentParser(description="Extract hole locations from PDFs")
    parser.add_argument("input_path", help="Path to PDF file or directory of PDFs")
    parser.add_argument("--output", default="hole_locations.csv", help="Output CSV file")
    parser.add_argument("--course", help="Override Course Name")
    parser.add_argument("--year", help="Override Year")
    parser.add_argument("--round", help="Override Round Number")
    args = parser.parse_args()

    all_data = []

    if os.path.isdir(args.input_path):
        for filename in os.listdir(args.input_path):
            if filename.lower().endswith(".pdf"):
                pdf_path = os.path.join(args.input_path, filename)
                print(f"Processing {pdf_path}...")
                try:
                    data = extract_hole_locations(pdf_path, args.course, args.year, args.round)
                    all_data.extend(data)
                except Exception as e:
                    print(f"Error processing {pdf_path}: {e}")
    elif os.path.isfile(args.input_path):
         print(f"Processing {args.input_path}...")
         try:
            data = extract_hole_locations(args.input_path, args.course, args.year, args.round)
            all_data.extend(data)
         except Exception as e:
            print(f"Error processing {args.input_path}: {e}")
    else:
        print("Invalid input path.")
        return

    if all_data:
        df = pd.DataFrame(all_data)
        # Reorder columns to match requirement
        cols = ["Year", "Course", "Round", "Hole", "Distance from Front", "Distance From Side", "Side", "Green Depth"]
        # Add missing cols if any
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        df = df[cols]

        df.to_csv(args.output, index=False)
        print(f"Successfully extracted {len(df)} records to {args.output}")
    else:
        print("No data extracted.")

if __name__ == "__main__":
    main()
