from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import geopandas as gpd
from census import Census
from us import states
import requests
from shapely.geometry import Point, Polygon
import json

def get_census_data(fips_code: str, year: int = 2022, api_key: str = None) -> pd.DataFrame:
    """
    Get Census demographic data for block groups in a given FIPS code.
    
    Args:
        fips_code (str): 5-digit FIPS code (state + county)
        year (int): Census year to query (default: 2022)
        api_key (str): Census API key. If None, will raise error.
    
    Returns:
        pd.DataFrame: DataFrame containing Census demographic data
        
    Raises:
        TypeError: If fips_code is not a string or year is not an int
        ValueError: If fips_code is not 5 digits or api_key is not provided
    """
    if not isinstance(fips_code, str):
        raise TypeError("fips_code must be a string")
    if not isinstance(year, int):
        raise TypeError("year must be an integer")
    if len(fips_code) != 5:
        raise ValueError("fips_code must be 5 digits (state + county)")
    if not api_key:
        raise ValueError("Census API key must be provided")

    # Initialize Census API
    c = Census(api_key)
    
    # Split FIPS code into state and county
    state_fips = fips_code[:2]
    county_fips = fips_code[2:]
    
    # Get block group data
    data = c.acs5.state_county_blockgroup(
        fields=['NAME',
                'B19013_001E',  # Median income
                'B01003_001E',  # Total population
                'B03002_003E',  # White alone
                'B03002_004E',  # Black alone
                'B03002_012E'],  # Hispanic/Latino
        state_fips=state_fips,
        county_fips=county_fips,
        blockgroup='*',  # All block groups
        year=year
    )

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Rename columns
    df = df.rename(columns={
        'B19013_001E': 'median_income',
        'B01003_001E': 'total_pop',
        'B03002_003E': 'white_pop',
        'B03002_004E': 'black_pop',
        'B03002_012E': 'hispanic_pop'
    })

    # Create GEOID for block groups (state+county+tract+block group)
    df['state_fips'] = df['state']
    df['county_fips'] = df['county']
    df['tract_fips'] = df['tract']
    df['bg_fips'] = df['block group']

    # Create standardized GEOID
    df['std_geoid'] = df['state_fips'] + df['county_fips'] + df['tract_fips'] + df['bg_fips']

    return df

def get_census_blockgroups_shapefile(fips_code: str) -> gpd.GeoDataFrame:
    """
    Get Census Block Group shapefiles for a given FIPS code from the Census TIGERweb service.
    
    Args:
        fips_code (str): 5-digit FIPS code (state + county)
    
    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing Census Block Group boundaries
        
    Raises:
        TypeError: If fips_code is not a string
        ValueError: If fips_code is not 5 digits
        requests.RequestException: If API request fails
    """
    if not isinstance(fips_code, str):
        raise TypeError("fips_code must be a string")
    if len(fips_code) != 5:
        raise ValueError("fips_code must be 5 digits (state + county)")

    # TIGERweb REST API endpoint
    base_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/2/query"
    
    # Query parameters
    params = {
        'where': f"STATE='{fips_code[:2]}' AND COUNTY='{fips_code[2:]}'",
        'outFields': '*',
        'returnGeometry': 'true',
        'f': 'geojson',
        'outSR': '4326'  # WGS84
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        geojson_data = response.json()
        
        # Convert to GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
        
        # Create standardized GEOID components
        gdf['state_fips'] = gdf['STATE']
        gdf['county_fips'] = gdf['COUNTY']
        gdf['tract_fips'] = gdf['TRACT']
        gdf['bg_fips'] = gdf['BLKGRP']

        # Create standardized GEOID
        gdf['std_geoid'] = gdf['state_fips'] + gdf['county_fips'] + gdf['tract_fips'] + gdf['bg_fips']
        
        return gdf
        
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch Census Block Group data: {str(e)}")

def match_to_census_blockgroups(
    gdf: gpd.GeoDataFrame,
    census_gdf: gpd.GeoDataFrame,
    join_type: str = "left"
) -> gpd.GeoDataFrame:
    """
    Match each row in a GeoDataFrame to its corresponding Census Block Group using spatial join.
    
    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame to match
        census_gdf (gpd.GeoDataFrame): Census Block Group boundaries GeoDataFrame
        join_type (str): Type of join to perform ('left', 'right', 'inner', 'outer')
    
    Returns:
        gpd.GeoDataFrame: Input GeoDataFrame with Census Block Group data appended
        
    Raises:
        TypeError: If inputs are not GeoDataFrames
        ValueError: If join_type is invalid
    """
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("gdf must be a GeoDataFrame")
    if not isinstance(census_gdf, gpd.GeoDataFrame):
        raise TypeError("census_gdf must be a GeoDataFrame")
    if join_type not in ['left', 'right', 'inner', 'outer']:
        raise ValueError("join_type must be one of: 'left', 'right', 'inner', 'outer'")

    # Ensure both GDFs have same CRS
    if gdf.crs != census_gdf.crs:
        census_gdf = census_gdf.to_crs(gdf.crs)

    # Use centroid of each geometry for the join to avoid issues with overlapping boundaries
    gdf_centroids = gdf.copy()
    gdf_centroids.geometry = gdf_centroids.geometry.centroid

    # Perform spatial join
    joined = gpd.sjoin(gdf_centroids, census_gdf, how=join_type, predicate='within')

    # Drop unnecessary columns from the join
    if 'index_right' in joined.columns:
        joined = joined.drop(columns=['index_right'])

    return joined

def get_census_data_with_boundaries(
    fips_code: str,
    year: int = 2022,
    api_key: str = None
) -> Tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """
    Get both Census demographic data and boundary files for block groups in a FIPS code.
    
    Args:
        fips_code (str): 5-digit FIPS code (state + county)
        year (int): Census year to query (default: 2022)
        api_key (str): Census API key
    
    Returns:
        Tuple[pd.DataFrame, gpd.GeoDataFrame]: 
            - Census demographic data DataFrame
            - Census Block Group boundaries GeoDataFrame
            
    Raises:
        TypeError: If inputs have wrong types
        ValueError: If inputs have invalid values
        requests.RequestException: If API requests fail
    """
    # Get demographic data
    census_data = get_census_data(fips_code, year, api_key)
    
    # Get boundary files
    census_boundaries = get_census_blockgroups_shapefile(fips_code)
    
    # Merge demographic data with boundaries
    # Use suffixes to avoid duplicate column names
    census_boundaries = census_boundaries.merge(
        census_data,
        on='std_geoid',
        how='left',
        suffixes=('', '_census')
    )
    
    # Drop duplicate columns that might have been created with the _census suffix
    census_boundaries = census_boundaries.loc[:, ~census_boundaries.columns.str.endswith('_census')]
    
    return census_data, census_boundaries

def enrich_shapefile_with_census(
    shapefile: Union[str, gpd.GeoDataFrame],
    fips_code: str,
    year: int = 2022,
    api_key: str = None
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Takes a shapefile (or GeoDataFrame) and enriches it with Census Block Group data.
    Also returns the Census Block Group data separately.
    
    Args:
        shapefile (Union[str, gpd.GeoDataFrame]): Either a path to a shapefile or a GeoDataFrame
        fips_code (str): 5-digit FIPS code (state + county)
        year (int): Census year to query (default: 2022)
        api_key (str): Census API key
    
    Returns:
        Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
            - Original shapefile enriched with Census Block Group data
            - Census Block Group boundaries with demographic data
            
    Raises:
        TypeError: If inputs have wrong types
        ValueError: If inputs have invalid values
        requests.RequestException: If API requests fail
        FileNotFoundError: If shapefile path is invalid
    """
    # Input validation
    if not isinstance(fips_code, str):
        raise TypeError("fips_code must be a string")
    if not isinstance(year, int):
        raise TypeError("year must be an integer")
    if len(fips_code) != 5:
        raise ValueError("fips_code must be 5 digits (state + county)")
    if not api_key:
        raise ValueError("Census API key must be provided")

    # Load the shapefile if string path provided
    if isinstance(shapefile, str):
        try:
            gdf = gpd.read_file(shapefile)
        except Exception as e:
            raise FileNotFoundError(f"Failed to read shapefile at {shapefile}: {str(e)}")
    elif isinstance(shapefile, gpd.GeoDataFrame):
        gdf = shapefile.copy()
    else:
        raise TypeError("shapefile must be either a file path (str) or a GeoDataFrame")
    
    # Check if the GeoDataFrame has a CRS and set one if it doesn't
    if gdf.crs is None:
        raise ValueError("Input GeoDataFrame must have a coordinate reference system (CRS) defined. "
                         "Use gdf.set_crs() to set a CRS before calling this function.")

    # Get census data and boundaries
    census_data, census_boundaries = get_census_data_with_boundaries(
        fips_code=fips_code,
        year=year,
        api_key=api_key
    )
    
    # Ensure census boundaries have a CRS
    if census_boundaries.crs is None:
        # Set a default CRS (EPSG:4326 - WGS84) if none exists
        census_boundaries = census_boundaries.set_crs("EPSG:4326")

    # Match shapefile to census block groups
    # Use a list of columns to keep from census_boundaries to avoid duplicates
    census_cols_to_keep = ['std_geoid', 'median_income', 'total_pop', 'white_pop', 
                          'black_pop', 'hispanic_pop']
    
    # First perform the spatial join
    enriched_gdf = match_to_census_blockgroups(
        gdf=gdf,
        census_gdf=census_boundaries[['geometry', 'std_geoid'] + 
                                    [col for col in census_cols_to_keep if col != 'std_geoid']],
        join_type="left"
    )

    return enriched_gdf, census_boundaries
