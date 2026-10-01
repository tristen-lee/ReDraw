import requests
import time

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "ReDraw/1.0 (tristen.lee1221@gmail.com)"}

def reverse_geocode(lat, lon):
    params = {"lat": lat, "lon": lon, "format": "jsonv2"}
    response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS)
    address = response.json()["address"]
    city = address.get("city") or address.get("town") or address.get("village")
    state = address.get("state")
    time.sleep(1)
    return f"{city}, {state}"

def get_locations(points):
    locations = set()
    for lon, lat in points[:5]:
        locations.add(reverse_geocode(lat, lon))
    return locations