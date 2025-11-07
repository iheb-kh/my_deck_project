from pathlib import Path
from pyproj import Transformer

"""
Hold global configuration and shared constants.
Input: none.
Output: constants imported by other modules.
"""

# server/ -> project root is parent of this directory
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'

BUILDINGS_FILE = DATA_DIR / 'BUILDINGS_GEOM_v1.parquet'
ROADS_FILE = DATA_DIR / 'GEOM_V1.parquet'
TRAFFIC_FILE = DATA_DIR / 'traffic_res.parquet'

VEHICLE_CLASSES = ['HW_truck', 'LMV_passengers', 'MHV_deliver', 'PWA_moped']

SIMPLIFY_TOLERANCE = 2e-5
BUCKET_SECONDS = 5

# Transformer from local CRS (EPSG:3003) to WGS84
transformer = Transformer.from_crs(3003, 4326, always_xy=True)
