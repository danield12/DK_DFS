import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import math
import csv
import re
import time

def get_pga_schedule():
    url = "https://www.provisualizer.com/procalendar/2025/men/pgatour.php"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching schedule: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')

    schedule = []

    rows = soup.find_all('tr')

    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue

        if len(cells) >= 4:
            # Usually: Date, Event, Venue, Links
            # But sometimes rowspans or unexpected structure.
            # We assume the structure is roughly consistent.

            # The Event Name might be in the 2nd cell (index 1)
            event_name = cells[1].get_text(strip=True)
            venue_name = cells[2].get_text(strip=True)

            # Links cell is usually the last one, or index 3.
            # Sometimes there are multiple link columns?
            # From curl: <td class="callink"><a href="/3dlink.php?id=2">3D</a></td>
            # The structure might be: Date, Event, Venue, 2D, 3D, Mobile, Guide, Website? (Multiple link columns)
            # view_text_website output showed "Links" header but that might be simplified.

            # Let's search all cells for a 3D link.
            link_3d = None
            for cell in cells:
                found = cell.find('a', href=re.compile(r'3dlink\.php\?id=\d+'))
                if found:
                    link_3d = found
                    break

            if link_3d:
                href = link_3d['href']
                match = re.search(r'id=(\d+)', href)
                if match:
                    course_id = match.group(1)
                    schedule.append({
                        'Tournament': event_name,
                        'Course': venue_name,
                        'id': course_id
                    })

    return schedule

def calculate_azimuth(lat1, lon1, lat2, lon2):
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dLon = lon2_rad - lon1_rad

    y = math.sin(dLon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dLon)

    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)

    # Normalize to 0-360
    bearing_deg = (bearing_deg + 360) % 360

    return bearing_deg

def distance_from_start(lat1, lon1, lat2, lon2):
    # Haversine distance in meters
    R = 6371000 # Radius of Earth in meters
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    d = R * c
    return d

def parse_kml_azimuths(kml_content):
    # Remove default namespace to simplify tag matching
    kml_content = re.sub(r' xmlns="[^"]+"', '', kml_content, count=1)

    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError:
        print("Error parsing KML content")
        return {}

    azimuths = {}

    # Find all elements that end with 'Tour' (handling namespaces like gx:Tour)
    tours = [elem for elem in root.iter() if elem.tag.endswith('Tour')]

    for tour in tours:
        # Robustly find 'name' child
        name_text = None
        for child in tour:
            if child.tag.endswith('name'):
                name_text = child.text
                break

        if not name_text:
            continue

        # Extract Hole Number
        match = re.search(r'Hole\s+(\d+)', name_text, re.IGNORECASE)
        if not match:
            continue
        hole_num = int(match.group(1))

        # Find Playlist
        # Playlist might be deeply nested or direct child
        playlist = None
        for elem in tour.iter():
            if elem.tag.endswith('Playlist'):
                playlist = elem
                break

        if playlist is None:
            continue

        # Extract all LookAt points
        lookats = []
        # Iterate over FlyTo elements in Playlist
        for elem in playlist.iter():
            if elem.tag.endswith('FlyTo'):
                # Find LookAt inside FlyTo
                lookat = None
                for sub in elem.iter():
                    if sub.tag.endswith('LookAt'):
                        lookat = sub
                        break

                if lookat is not None:
                    lat_elem = None
                    lon_elem = None
                    for sub in lookat:
                        if sub.tag.endswith('latitude'):
                            lat_elem = sub
                        elif sub.tag.endswith('longitude'):
                            lon_elem = sub

                    if lat_elem is not None and lon_elem is not None:
                        try:
                            lat = float(lat_elem.text)
                            lon = float(lon_elem.text)
                            lookats.append((lat, lon))
                        except ValueError:
                            pass

        if not lookats:
            continue

        start_pt = lookats[0]

        # Determine Green location
        # Filter out the return leg if it exists
        cutoff_index = len(lookats)
        # Scan backwards from the end
        for i in range(len(lookats) - 1, len(lookats) // 2, -1):
            dist = distance_from_start(start_pt[0], start_pt[1], lookats[i][0], lookats[i][1])
            # If we are very close to start, we are likely back at tee
            if dist < 40: # 40 meters threshold
                cutoff_index = i
            else:
                # If we are far from start, we are likely at the green or approaching it from return leg?
                # The assumption is: Tee -> Fairway -> Green -> Return -> Tee
                # So the sequence of distances goes: 0 -> increasing -> Max -> decreasing -> 0
                pass

        # Truncate the return leg
        outbound_leg = lookats[:cutoff_index]

        # If truncation removed everything (e.g. circle?), fallback
        if not outbound_leg:
            outbound_leg = lookats

        # Green is the point with max distance from start in the outbound leg
        max_dist = -1
        green_pt = None

        for pt in outbound_leg:
            d = distance_from_start(start_pt[0], start_pt[1], pt[0], pt[1])
            if d > max_dist:
                max_dist = d
                green_pt = pt

        if green_pt:
            az = calculate_azimuth(start_pt[0], start_pt[1], green_pt[0], green_pt[1])
            azimuths[hole_num] = round(az, 2)

    return azimuths

def main():
    print("Fetching schedule...")
    schedule = get_pga_schedule()
    print(f"Found {len(schedule)} courses.")

    results = []

    # Header for CSV
    fieldnames = ['Tournament', 'Course'] + [str(i) for i in range(1, 19)]

    for i, item in enumerate(schedule):
        print(f"Processing {i+1}/{len(schedule)}: {item['Tournament']} - {item['Course']} (ID: {item['id']})")

        kml_url = f"https://www.provisualizer.com/flyoverlink.php?id={item['id']}"
        try:
            response = requests.get(kml_url, timeout=30)
            if response.status_code == 200:
                kml_content = response.text
                azimuths = parse_kml_azimuths(kml_content)

                row = {
                    'Tournament': item['Tournament'],
                    'Course': item['Course']
                }
                for h in range(1, 19):
                    row[str(h)] = azimuths.get(h, '')

                results.append(row)
            else:
                print(f"Failed to fetch KML: {response.status_code}")

        except Exception as e:
            print(f"Error processing {item['Course']}: {e}")

        time.sleep(1)

    with open('pga_course_azimuths_2025.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print("Done. Saved to pga_course_azimuths_2025.csv")

if __name__ == "__main__":
    main()
