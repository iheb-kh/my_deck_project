from typing import List
from shapely.ops import transform as shapely_transform
from shapely.geometry import mapping

from .app_config import SIMPLIFY_TOLERANCE, transformer
from .data_loaders import load_roads

"""
Prepare and cache road geometries in WGS84.
Input: roads data via load_roads.
Output: IDs, index map, geometries, FeatureCollection.
"""


def build_roads_cache():
    """
    Build cached roads FeatureCollection and index.
    Input: none.
    Output: (ids list, id_to_index dict, geometries list, roads_fc).
    """
    df = load_roads()

    ids: List[str] = []
    geometries = []

    for _, row in df.iterrows():
        geom = row['geometry_obj']
        if geom is None:
            continue

        geom = shapely_transform(transformer.transform, geom)

        try:
            geom = geom.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        except Exception:
            pass

        geometries.append(mapping(geom))
        ids.append(str(row['id']))

    id_to_index = {rid: i for i, rid in enumerate(ids)}

    roads_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": geometries[i],
                "properties": {"id": ids[i]},
            }
            for i in range(len(ids))
        ],
    }

    return ids, id_to_index, geometries, roads_fc


ROAD_IDS, ID_TO_INDEX, GEOMETRIES, ROADS_FC = build_roads_cache()
