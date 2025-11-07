from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform
from .app_config import transformer

"""
Utility functions for geometry operations.
Input: shapely geometries.
Output: transformed geometries and GeoJSON.
"""


def convert_geometry_to_wgs84(geometry):
    """
    Reproject geometry from EPSG:3003 to EPSG:4326.
    Input: shapely geometry or None.
    Output: transformed geometry or original/None.
    """
    if geometry is None:
        return None
    try:
        return shapely_transform(transformer.transform, geometry)
    except Exception:
        return geometry


def geometry_to_geojson(geometry):
    """
    Convert shapely geometry to GeoJSON dict.
    Input: shapely geometry or None.
    Output: GeoJSON mapping or None.
    """
    if geometry is None:
        return None
    try:
        return mapping(geometry)
    except Exception:
        return None
