import pandas as pd
from shapely import wkb
from .app_config import BUILDINGS_FILE, ROADS_FILE, TRAFFIC_FILE

"""
Functions to load raw data from parquet files.
Input: none (uses paths from app_config).
Output: pandas DataFrames.
"""


def load_buildings() -> pd.DataFrame:
    """
    Load building data and parse WKB geometry.
    Input: none.
    Output: DataFrame with 'geometry_obj' column.
    """
    df = pd.read_parquet(BUILDINGS_FILE)
    df['geometry_obj'] = df['geometry'].apply(
        lambda x: wkb.loads(x) if x is not None else None
    )
    return df


def load_roads() -> pd.DataFrame:
    """
    Load roads data and parse WKB geometry.
    Input: none.
    Output: DataFrame with 'geometry_obj' and string 'id'.
    """
    df = pd.read_parquet(ROADS_FILE)
    df['geometry_obj'] = df['geometry'].apply(
        lambda x: wkb.loads(x) if x is not None else None
    )
    df['id'] = df['id'].astype(str)
    return df


def load_raw_traffic() -> pd.DataFrame:
    """
    Load raw traffic data and compute time in seconds.
    Input: none.
    Output: DataFrame with begin/end and begin_seconds/end_seconds.
    """
    df = pd.read_parquet(TRAFFIC_FILE)

    df['begin'] = pd.to_datetime(df['begin'], utc=True)
    df['end'] = pd.to_datetime(df['end'], utc=True)

    df['begin_seconds'] = (df['begin'].view('int64') // 1_000_000_000).astype(int)
    df['end_seconds'] = (df['end'].view('int64') // 1_000_000_000).astype(int)

    if 'id' in df.columns:
        df['id'] = df['id'].astype(str)

    return df
