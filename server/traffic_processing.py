from typing import Optional, Dict, List, Tuple
from functools import lru_cache
import re

import numpy as np
import pandas as pd

from .app_config import VEHICLE_CLASSES, BUCKET_SECONDS
from .data_loaders import load_raw_traffic

"""
Build traffic metrics and cached GeoJSON frames.
Input: raw traffic from data_loaders.
Output: processed DataFrame, arrays, frame builder.
"""


def convert_to_safe_float(value):
    """
    Convert a value to float safely.
    Input: number or string.
    Output: float or None.
    """
    try:
        number = float(value)
        if np.isfinite(number):
            return number
    except Exception:
        pass
    return None


def calculate_weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """
    Compute weighted mean.
    Input: values array, weights array.
    Output: float mean or np.nan.
    """
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def bucket_timestamp(timestamp_seconds: int) -> int:
    """
    Snap timestamp to bucket.
    Input: timestamp in seconds.
    Output: bucketed timestamp.
    """
    return int(timestamp_seconds - (timestamp_seconds % BUCKET_SECONDS))


VCLASS_MAPPING_RULES: List[Tuple[str, str]] = [
    (r'(truck|hgv|lorry|heavy)', 'HW_truck'),
    (r'(van|deliver|mhv|medium)', 'MHV_deliver'),
    (r'(moped|scooter|motorbike|motorcycle|bike|2w|twowheeler|ptw|pwa)', 'PWA_moped'),
    (r'(car|pass|lmv|light|auto|passenger)', 'LMV_passengers'),
]


def map_vehicle_class(raw_vclass: str) -> Optional[str]:
    """
    Map raw vehicle class text.
    Input: raw_vclass as string.
    Output: canonical class or None.
    """
    value = (raw_vclass or '').lower()
    for pattern, canonical in VCLASS_MAPPING_RULES:
        if re.search(pattern, value):
            return canonical
    return None


def build_traffic_dataframe() -> pd.DataFrame:
    """
    Build full traffic metrics table.
    Input: none.
    Output: DataFrame used by traffic API.
    """
    df = load_raw_traffic().copy()
    has_vclass = 'vclass' in df.columns

    # Case 1: vclass rows -> group
    if has_vclass:
        if {'entered', 'left'}.issubset(df.columns):
            df['_row_count'] = (
                pd.to_numeric(df['entered'], errors='coerce').fillna(0)
                + pd.to_numeric(df['left'], errors='coerce').fillna(0)
            ) / 2.0
        elif {'arrived', 'departed'}.issubset(df.columns):
            df['_row_count'] = (
                pd.to_numeric(df['arrived'], errors='coerce').fillna(0)
                + pd.to_numeric(df['departed'], errors='coerce').fillna(0)
            ) / 2.0
        else:
            df['_row_count'] = 0.0

        df['_canon_class'] = df['vclass'].astype(str).map(map_vehicle_class)

        group_cols = ['id', 'begin', 'end', 'begin_seconds', 'end_seconds', '_canon_class']
        grouped = df.groupby(group_cols, dropna=True)

        counts = grouped['_row_count'].sum().rename('count').reset_index()

        if 'speed' in df.columns:
            df['_weighted_speed'] = pd.to_numeric(
                df['speed'], errors='coerce'
            ) * df['_row_count']
            speed_sum = grouped['_weighted_speed'].sum().rename('w_speed')
            count_sum = grouped['_row_count'].sum().rename('w_count')
            tmp = pd.concat([speed_sum, count_sum], axis=1).reset_index()
            tmp['mean_speed'] = tmp.apply(
                lambda r: r['w_speed'] / r['w_count']
                if r['w_count'] > 0 else np.nan,
                axis=1,
            )
        else:
            tmp = counts.copy()
            tmp['mean_speed'] = np.nan

        counts_wide = counts.pivot_table(
            index=['id', 'begin', 'end', 'begin_seconds', 'end_seconds'],
            columns='_canon_class',
            values='count',
            aggfunc='sum',
            fill_value=0.0,
        )
        speed_wide = tmp.pivot_table(
            index=['id', 'begin', 'end', 'begin_seconds', 'end_seconds'],
            columns='_canon_class',
            values='mean_speed',
            aggfunc='mean',
        )

        counts_wide = counts_wide.rename_axis(None, axis=1)
        speed_wide = speed_wide.rename_axis(None, axis=1)

        full_index = counts_wide.index.union(speed_wide.index)
        counts_wide = counts_wide.reindex(full_index).copy()
        speed_wide = speed_wide.reindex(full_index).copy()

        for klass in VEHICLE_CLASSES:
            if klass not in counts_wide.columns:
                counts_wide[klass] = 0.0
            if klass not in speed_wide.columns:
                speed_wide[klass] = np.nan

        counts_wide = counts_wide[VEHICLE_CLASSES].apply(
            pd.to_numeric, errors='coerce'
        ).fillna(0.0)
        speed_wide = speed_wide[VEHICLE_CLASSES].apply(
            pd.to_numeric, errors='coerce'
        )

        base = counts_wide.copy()
        base['vehicles'] = base[VEHICLE_CLASSES].sum(axis=1)

        counts_array = base[VEHICLE_CLASSES].to_numpy(float)
        speeds_array = speed_wide[VEHICLE_CLASSES].to_numpy(float)

        blended = [
            calculate_weighted_mean(speeds_array[i, :], counts_array[i, :])
            for i in range(len(base))
        ]
        base['speed'] = blended

        baseline_speed = base.groupby(level=0)['speed'].quantile(0.95).replace(0, np.nan)

        def get_baseline_speed(idx):
            """
            Get baseline speed for a road.
            Input: multi-index tuple.
            Output: float baseline or NaN.
            """
            road_id = idx[0]
            return baseline_speed.get(road_id, np.nan)

        base['speedRelative'] = base.apply(
            lambda r: (
                r['speed'] / get_baseline_speed(r.name)
                if pd.notna(get_baseline_speed(r.name)) else np.nan
            ),
            axis=1,
        ).clip(lower=0)

        per_class_rel = {}
        for klass in VEHICLE_CLASSES:
            series_c = speed_wide[klass]
            baseline_c = series_c.groupby(level=0).quantile(0.95).replace(0, np.nan)

            def get_class_baseline(idx):
                """
                Get baseline for class speed.
                Input: multi-index tuple.
                Output: float baseline or NaN.
                """
                road_id = idx[0]
                return baseline_c.get(road_id, np.nan)

            rel_vals = []
            for idx_val, val in series_c.items():
                b = get_class_baseline(idx_val)
                rel_vals.append(val / b if pd.notna(b) else np.nan)

            per_class_rel[klass] = pd.Series(
                rel_vals, index=series_c.index, name=f'{klass}_rel'
            ).clip(lower=0)

        speed_wide_s = speed_wide.add_suffix('_s')
        rel_wide = pd.concat(
            [per_class_rel[c] for c in VEHICLE_CLASSES], axis=1
        )

        combined = pd.concat(
            [base[['vehicles', 'speed', 'speedRelative']],
             counts_wide,
             speed_wide_s,
             rel_wide],
            axis=1,
        ).reset_index()

        cols = (
            ['id', 'begin', 'end', 'vehicles', 'speed', 'speedRelative']
            + VEHICLE_CLASSES
            + [f'{c}_s' for c in VEHICLE_CLASSES]
            + [f'{c}_rel' for c in VEHICLE_CLASSES]
            + ['begin_seconds', 'end_seconds']
        )
        return combined[cols]

    # Case 2: already aggregated
    for klass in VEHICLE_CLASSES:
        if klass not in df.columns:
            df[klass] = 0.0
    for klass in VEHICLE_CLASSES:
        s_col = f'{klass}_s'
        if s_col not in df.columns:
            df[s_col] = np.nan

    if {'entered', 'left'}.issubset(df.columns):
        df['vehicles'] = (
            pd.to_numeric(df['entered'], errors='coerce').fillna(0)
            + pd.to_numeric(df['left'], errors='coerce').fillna(0)
        ) / 2.0
    else:
        df['vehicles'] = (
            df[VEHICLE_CLASSES]
            .apply(pd.to_numeric, errors='coerce')
            .fillna(0)
            .sum(axis=1)
        )

    counts_array = (
        df[VEHICLE_CLASSES]
        .apply(pd.to_numeric, errors='coerce')
        .fillna(0)
        .to_numpy(float)
    )
    speeds_array = (
        df[[f'{c}_s' for c in VEHICLE_CLASSES]]
        .apply(pd.to_numeric, errors='coerce')
        .to_numpy(float)
    )

    blended = [
        calculate_weighted_mean(speeds_array[i, :], counts_array[i, :])
        for i in range(len(df))
    ]
    df['speed'] = blended

    baseline_speed = df.groupby('id')['speed'].quantile(0.95).replace(0, np.nan)
    df['speedRelative'] = df.apply(
        lambda r: (
            r['speed'] / baseline_speed.get(r['id'], np.nan)
            if pd.notna(baseline_speed.get(r['id'], np.nan)) else np.nan
        ),
        axis=1,
    ).clip(lower=0)

    for klass in VEHICLE_CLASSES:
        s_col = f'{klass}_s'
        baseline_c = df.groupby('id')[s_col].quantile(0.95).replace(0, np.nan)
        df[f'{klass}_rel'] = df.apply(
            lambda r, col=s_col: (
                r[col] / baseline_c.get(r['id'], np.nan)
                if pd.notna(baseline_c.get(r['id'], np.nan)) else np.nan
            ),
            axis=1,
        ).clip(lower=0)

    cols = (
        ['id', 'begin', 'end', 'vehicles', 'speed', 'speedRelative']
        + VEHICLE_CLASSES
        + [f'{c}_s' for c in VEHICLE_CLASSES]
        + [f'{c}_rel' for c in VEHICLE_CLASSES]
        + ['begin_seconds', 'end_seconds']
    )
    return df[cols]


# Build once
TRAFFIC_DF = build_traffic_dataframe()

VEHICLES_ALL = TRAFFIC_DF['vehicles'].to_numpy(float)
SPEED_ALL = TRAFFIC_DF['speed'].to_numpy(float)
RELATIVE_ALL = TRAFFIC_DF['speedRelative'].to_numpy(float)
BEGIN_SECONDS = TRAFFIC_DF['begin_seconds'].to_numpy(int)
END_SECONDS = TRAFFIC_DF['end_seconds'].to_numpy(int)
ROAD_ID_ARRAY = TRAFFIC_DF['id'].astype(str).to_numpy()

CLASS_COUNTS = {c: TRAFFIC_DF[c].to_numpy(float) for c in VEHICLE_CLASSES}
CLASS_SPEEDS = {c: TRAFFIC_DF[f'{c}_s'].to_numpy(float) for c in VEHICLE_CLASSES}
CLASS_RELATIVE = {c: TRAFFIC_DF[f'{c}_rel'].to_numpy(float) for c in VEHICLE_CLASSES}


@lru_cache(maxsize=4096)
def build_traffic_frame_geojson(bucket: int, vehicle_class: str, metric: str) -> dict:
    """
    Build one traffic frame as GeoJSON.
    Input: bucket seconds, vehicle_class, metric.
    Output: FeatureCollection + stats.
    """
    from .roads_cache import ID_TO_INDEX, GEOMETRIES  # local to avoid cycle

    window_start = bucket - BUCKET_SECONDS
    window_end = bucket + BUCKET_SECONDS

    mask = (END_SECONDS >= window_start) & (BEGIN_SECONDS <= window_end)
    indices = np.nonzero(mask)[0]

    if metric == 'count':
        values = VEHICLES_ALL if vehicle_class == 'all' else CLASS_COUNTS[vehicle_class]
    elif metric == 'speed':
        values = SPEED_ALL if vehicle_class == 'all' else CLASS_SPEEDS[vehicle_class]
    else:
        values = RELATIVE_ALL if vehicle_class == 'all' else CLASS_RELATIVE[vehicle_class]

    window_values = values[indices]
    finite = np.isfinite(window_values)

    if finite.any():
        vmin = float(np.nanmin(window_values[finite]))
        vmax = float(np.nanmax(window_values[finite]))
    else:
        vmin, vmax = 0.0, 1.0

    features = []

    for i in indices.tolist():
        road_id = ROAD_ID_ARRAY[i]
        geom_index = ID_TO_INDEX.get(road_id)
        if geom_index is None:
            continue

        props = {
            "id": road_id,
            "begin": TRAFFIC_DF['begin'].iloc[i].isoformat(),
            "end": TRAFFIC_DF['end'].iloc[i].isoformat(),
            "vehicles": convert_to_safe_float(VEHICLES_ALL[i]),
            "speed": convert_to_safe_float(SPEED_ALL[i]),
            "speedRelative": convert_to_safe_float(RELATIVE_ALL[i]),
            "HW_truck": convert_to_safe_float(CLASS_COUNTS['HW_truck'][i]),
            "LMV_passengers": convert_to_safe_float(CLASS_COUNTS['LMV_passengers'][i]),
            "MHV_deliver": convert_to_safe_float(CLASS_COUNTS['MHV_deliver'][i]),
            "PWA_moped": convert_to_safe_float(CLASS_COUNTS['PWA_moped'][i]),
            "HW_truck_s": convert_to_safe_float(CLASS_SPEEDS['HW_truck'][i]),
            "LMV_passengers_s": convert_to_safe_float(CLASS_SPEEDS['LMV_passengers'][i]),
            "MHV_deliver_s": convert_to_safe_float(CLASS_SPEEDS['MHV_deliver'][i]),
            "PWA_moped_s": convert_to_safe_float(CLASS_SPEEDS['PWA_moped'][i]),
            "HW_truck_rel": convert_to_safe_float(CLASS_RELATIVE['HW_truck'][i]),
            "LMV_passengers_rel": convert_to_safe_float(CLASS_RELATIVE['LMV_passengers'][i]),
            "MHV_deliver_rel": convert_to_safe_float(CLASS_RELATIVE['MHV_deliver'][i]),
            "PWA_moped_rel": convert_to_safe_float(CLASS_RELATIVE['PWA_moped'][i]),
            "value": convert_to_safe_float(values[i]),
        }

        features.append({
            "type": "Feature",
            "geometry": GEOMETRIES[geom_index],
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "stats": {
            "min": vmin,
            "max": vmax,
            "veh_class": vehicle_class,
            "metric": metric,
        },
    }
