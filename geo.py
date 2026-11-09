"""
Geo helpers for shipment tracking — no paid map/geocoding API needed.
A built-in table of Pakistani cities turns an address text into coordinates.
"""
import math
import re

# name -> (latitude, longitude)
CITIES = {
    'Karachi': (24.8607, 67.0011),       'Lahore': (31.5204, 74.3587),
    'Islamabad': (33.6844, 73.0479),     'Rawalpindi': (33.5651, 73.0169),
    'Faisalabad': (31.4504, 73.1350),    'Multan': (30.1575, 71.5249),
    'Hyderabad': (25.3960, 68.3578),     'Peshawar': (34.0151, 71.5249),
    'Quetta': (30.1798, 66.9750),        'Sialkot': (32.4945, 74.5229),
    'Gujranwala': (32.1877, 74.1945),    'Bahawalpur': (29.3956, 71.6836),
    'Sargodha': (32.0740, 72.6861),      'Sukkur': (27.7052, 68.8574),
    'Larkana': (27.5570, 68.2028),       'Sahiwal': (30.6682, 73.1114),
    'Okara': (30.8138, 73.4534),         'Rahim Yar Khan': (28.4202, 70.2952),
    'Dera Ghazi Khan': (30.0561, 70.6403), 'Jhang': (31.2681, 72.3181),
    'Sheikhupura': (31.7167, 73.9850),   'Gujrat': (32.5731, 74.0750),
    'Mardan': (34.1986, 72.0404),        'Abbottabad': (34.1688, 73.2215),
    'Mirpur Khas': (25.5276, 69.0159),   'Nawabshah': (26.2442, 68.4100),
    'Khanewal': (30.3017, 71.9321),      'Vehari': (30.0452, 72.3489),
    'Muzaffargarh': (30.0736, 71.1930),  'Lodhran': (29.5339, 71.6324),
    'Kasur': (31.1187, 74.4500),         'Jhelum': (32.9345, 73.7310),
    'Chiniot': (31.7292, 72.9822),       'Mianwali': (32.5839, 71.5370),
    'Khuzdar': (27.8000, 66.6167),       'Gwadar': (25.1216, 62.3254),
    'Bahawalnagar': (29.9987, 73.2536),  'Pakpattan': (30.3436, 73.3894),
    'Burewala': (30.1667, 72.6500),      'Kohat': (33.5869, 71.4414),
    'Swat': (34.7717, 72.3600),          'Murree': (33.9070, 73.3943),
}

# longest names first so "Rahim Yar Khan" wins over shorter partial matches
_PATTERNS = [(name, re.compile(r'\b' + re.escape(name) + r'\b', re.I))
             for name in sorted(CITIES, key=len, reverse=True)]


def resolve(text):
    """Return (lat, lng, city) for the first known city found in `text`, else None."""
    if not text:
        return None
    for name, pat in _PATTERNS:
        if pat.search(text):
            lat, lng = CITIES[name]
            return lat, lng, name
    return None


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_city(lat, lng, exclude=()):
    names = [n for n in CITIES if n not in exclude] or list(CITIES)
    name = min(names, key=lambda n: haversine_km(lat, lng, *CITIES[n]))
    return name, haversine_km(lat, lng, *CITIES[name])


def interpolate(a, b, f):
    """Point at fraction f (0..1) on the straight line a -> b, both (lat, lng)."""
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
