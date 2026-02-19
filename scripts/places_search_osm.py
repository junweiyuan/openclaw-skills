#!/usr/bin/env python3
"""
Keyless nearby places search using OpenStreetMap services.
- Geocoding: Nominatim
- POI search: Overpass API

Usage:
  python3 scripts/places_search_osm.py --near "Mountain View, CA" --query ramen --limit 8
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


def http_get_json(url: str, headers: dict | None = None, timeout: int = 25):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def http_post_text(url: str, body: str, headers: dict | None = None, timeout: int = 40):
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def geocode(place: str):
    q = urllib.parse.urlencode({"q": place, "format": "jsonv2", "limit": 1})
    url = f"{NOMINATIM}?{q}"
    data = http_get_json(
        url,
        headers={
            "User-Agent": "openclaw-osm-places/1.0 (local assistant)",
            "Accept": "application/json",
        },
    )
    if not data:
        raise RuntimeError(f"Location not found: {place}")
    item = data[0]
    return float(item["lat"]), float(item["lon"]), item.get("display_name", place)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_overpass_query(lat: float, lon: float, radius_m: int, query: str):
    q = query.lower().strip()
    if "ramen" in q:
        filter_expr = '["amenity"="restaurant"]["cuisine"~"ramen|japanese",i]'
    elif "coffee" in q or "cafe" in q:
        filter_expr = '["amenity"~"cafe|coffee_shop",i]'
    elif "pizza" in q:
        filter_expr = '["amenity"="restaurant"]["cuisine"~"pizza|italian",i]'
    else:
        filter_expr = '["amenity"~"restaurant|fast_food|cafe",i]'

    return f"""
[out:json][timeout:25];
(
  node{filter_expr}(around:{radius_m},{lat},{lon});
  way{filter_expr}(around:{radius_m},{lat},{lon});
  relation{filter_expr}(around:{radius_m},{lat},{lon});
);
out center tags;
""".strip()


def search_places(lat: float, lon: float, query: str, radius_m: int, limit: int):
    overpass_q = build_overpass_query(lat, lon, radius_m, query)

    last_err = None
    data = None
    for endpoint in OVERPASS_ENDPOINTS:
        for _ in range(2):  # light retry per endpoint
            try:
                raw = http_post_text(
                    endpoint,
                    overpass_q,
                    headers={
                        "User-Agent": "openclaw-osm-places/1.0 (local assistant)",
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
                data = json.loads(raw)
                break
            except Exception as e:
                last_err = e
        if data is not None:
            break

    if data is None:
        raise RuntimeError(f"All Overpass endpoints failed: {last_err}")

    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if "lat" in el and "lon" in el:
            plat, plon = el["lat"], el["lon"]
        else:
            c = el.get("center") or {}
            plat, plon = c.get("lat"), c.get("lon")
        if plat is None or plon is None:
            continue

        dist = haversine_km(lat, lon, float(plat), float(plon))
        cuisine = tags.get("cuisine", "-")
        amenity = tags.get("amenity", "-")
        out.append(
            {
                "name": name,
                "distance_km": round(dist, 2),
                "cuisine": cuisine,
                "type": amenity,
                "lat": float(plat),
                "lon": float(plon),
            }
        )

    out.sort(key=lambda x: x["distance_km"])

    dedup = []
    seen = set()
    for p in out:
        key = (p["name"].lower(), round(p["lat"], 4), round(p["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(p)
        if len(dedup) >= limit:
            break

    return dedup


def main():
    ap = argparse.ArgumentParser(description="Search nearby places with OpenStreetMap (no API key).")
    ap.add_argument("--near", required=True, help="Place/city to search near")
    ap.add_argument("--query", default="restaurant", help="What to find, e.g. ramen, coffee")
    ap.add_argument("--radius", type=int, default=3000, help="Search radius in meters")
    ap.add_argument("--limit", type=int, default=8, help="Max results")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    lat, lon, display = geocode(args.near)
    results = search_places(lat, lon, args.query, max(500, min(args.radius, 30000)), max(1, min(args.limit, 30)))

    if args.json:
        print(json.dumps({"near": display, "query": args.query, "count": len(results), "results": results}, ensure_ascii=False, indent=2))
        return

    print(f"🔎 {args.query} near {display}")
    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['name']} — {r['distance_km']} km | {r['cuisine']} | {r['type']}")
        print(f"   https://www.openstreetmap.org/?mlat={r['lat']}&mlon={r['lon']}#map=17/{r['lat']}/{r['lon']}")


if __name__ == "__main__":
    main()
