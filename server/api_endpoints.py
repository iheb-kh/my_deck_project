from typing import Optional
import pandas as pd
from fastapi import Query
from fastapi.responses import ORJSONResponse as JSONResponse
from nicegui import app

from .data_loaders import load_buildings, load_roads
from .geometry_utils import convert_geometry_to_wgs84, geometry_to_geojson
from .roads_cache import ROADS_FC
from .traffic_processing import (
    TRAFFIC_DF,
    bucket_timestamp,
    build_traffic_frame_geojson,
)

"""
HTTP API endpoints for map data.
Input: HTTP requests.
Output: GeoJSON/JSON responses for frontend.
"""


@app.get('/api/map/buildings')
def api_get_buildings(limit: int = Query(1000)):
    """
    Return building geometries as GeoJSON.
    Input: limit (max number of features).
    Output: FeatureCollection of buildings.
    """
    df = load_buildings()
    if limit:
        df = df.head(limit)

    features = []
    for _, row in df.iterrows():
        geom = row['geometry_obj']
        if geom is None:
            continue

        g_wgs = convert_geometry_to_wgs84(geom)
        gj = geometry_to_geojson(g_wgs)

        if gj:
            features.append({
                "type": "Feature",
                "geometry": gj,
                "properties": {
                    "PK": row.get("PK"),
                    "HEIGHT": float(row["HEIGHT"]) if pd.notna(row.get("HEIGHT")) else None,
                    "POP": float(row["POP"]) if pd.notna(row.get("POP")) else None,
                },
            })

    return JSONResponse({"type": "FeatureCollection", "features": features})


@app.get('/api/map/roads_static')
def api_get_roads_static():
    """
    Return cached static roads FeatureCollection.
    Input: none.
    Output: FeatureCollection of roads.
    """
    return JSONResponse(ROADS_FC)


@app.get('/api/map/roads')
def api_get_roads(limit: int = Query(1000)):
    """
    Return road geometries as GeoJSON.
    Input: limit (max features).
    Output: FeatureCollection of roads.
    """
    df = load_roads()
    if limit:
        df = df.head(limit)

    features = []
    for _, row in df.iterrows():
        geom = row['geometry_obj']
        if geom is None:
            continue

        g_wgs = convert_geometry_to_wgs84(geom)
        gj = geometry_to_geojson(g_wgs)

        if gj:
            features.append({
                "type": "Feature",
                "geometry": gj,
                "properties": {
                    "PK": row.get("PK"),
                    "id": row["id"],
                },
            })

    return JSONResponse({"type": "FeatureCollection", "features": features})


@app.get('/api/map/traffic')
def api_get_traffic(
    fr: Optional[int] = Query(None, alias='fr'),
    to: Optional[int] = Query(None, alias='to'),
    veh_class: str = Query(
        'all',
        pattern='^(all|HW_truck|LMV_passengers|MHV_deliver|PWA_moped)$',
    ),
    metric: str = Query(
        'relative',
        pattern='^(count|speed|relative)$',
    ),
):
    """
    Return one traffic frame for selected filters.
    Input: fr/to seconds, veh_class, metric.
    Output: FeatureCollection with stats.
    """
    if fr is None and to is None:
        middle = int(TRAFFIC_DF['begin_seconds'].min())
    else:
        start_value = int(fr or TRAFFIC_DF['begin_seconds'].min())
        end_value = int(to or TRAFFIC_DF['end_seconds'].max())
        middle = (start_value + end_value) // 2

    bucket = bucket_timestamp(middle)
    frame = build_traffic_frame_geojson(bucket, veh_class, metric)
    return JSONResponse(frame)


@app.get('/api/map/meta')
def api_get_metadata():
    """
    Return metadata for time range and viewport.
    Input: none.
    Output: JSON with traffic_time_range and viewport.
    """
    td = TRAFFIC_DF
    return JSONResponse({
        "traffic_time_range": {
            "min": int(td["begin_seconds"].min()),
            "max": int(td["begin_seconds"].max() if False else td["end_seconds"].max()),
        },
        "viewport": {
            "longitude": 10.3967,
            "latitude": 43.7167,
            "zoom": 13,
        },
    })
