import requests
import pandas as pd
from io import BytesIO
from datetime import datetime
import json
from shapely.geometry import Polygon
import geopandas as gpd
from azure.storage.blob import BlobServiceClient

def get_feature_data_with_geometry(dataset_name, base_url,layer_id=0):
    """Get all features from a service including geometry with pagination"""
    url = f"{base_url}/{dataset_name}/FeatureServer/{layer_id}/query"
    
    # First, get the count of all features
    count_params = {
        'f': 'json',
        'where': '1=1',
        'returnCountOnly': 'true'
    }
    
    try:
        count_response = requests.get(url, params=count_params)
        count_response.raise_for_status()
        total_records = count_response.json().get('count', 0)
        
        print(f"Total records in {dataset_name}: {total_records}")
        
        # Now fetch the actual data in chunks
        all_features = []
        offset = 0
        chunk_size = 2000  # ArcGIS typically limits to 2000 records per request
        
        while offset < total_records:
            params = {
                'f': 'json',
                'where': '1=1',
                'outFields': '*',
                'returnGeometry': 'true',
                'geometryPrecision': 6,
                'resultOffset': offset,
                'resultRecordCount': chunk_size
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'features' in data:
                # Convert ESRI features to GeoDataFrame format
                for feature in data['features']:
                    # Extract attributes
                    attributes = feature['attributes']
                    
                    # Convert ESRI rings to Shapely polygon
                    if feature['geometry'] and 'rings' in feature['geometry']:
                        # Take the first ring (exterior ring)
                        ring = feature['geometry']['rings'][0]
                        # Create Shapely polygon
                        polygon = Polygon(ring)
                        
                        # Combine attributes and geometry
                        attributes['geometry'] = polygon
                        all_features.append(attributes)
                
                print(f"Fetched records {offset} to {offset + len(data['features'])} of {total_records}")
                
                if len(data['features']) < chunk_size:
                    break
                    
                offset += chunk_size
            else:
                print(f"No features found in response for {dataset_name}")
                break
        
        if all_features:
            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(all_features, crs='EPSG:3857')  # Web Mercator
            
            # Convert to WGS84
            gdf = gdf.to_crs('EPSG:4326')
            
            return gdf
        
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {dataset_name}: {e}")
        return None


def get_feature_data(dataset_name, base_url, layer_id=0):
    """
    Get all features from a service using pagination
    
    Args:
        dataset_name (str): Name of the dataset to fetch
        base_url (str): Base URL for the feature service
        layer_id (int, optional): Layer ID to query. Defaults to 0.
    """
    url = f"{base_url}/{dataset_name}/FeatureServer/{layer_id}/query"
    
    # First, get the count of all features
    count_params = {
        'f': 'json',
        'where': '1=1',
        'returnCountOnly': 'true'
    }
    
    try:
        count_response = requests.get(url, params=count_params)
        count_response.raise_for_status()
        total_records = count_response.json().get('count', 0)
        
        print(f"Total records in {dataset_name}: {total_records}")
        
        # Now fetch the actual data in chunks
        all_features = []
        offset = 0
        chunk_size = 2000  # ArcGIS typically limits to 2000 records per request
        
        while offset < total_records:
            params = {
                'f': 'json',
                'where': '1=1',
                'outFields': '*',
                'returnGeometry': 'false',
                'resultOffset': offset,
                'resultRecordCount': chunk_size
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'features' in data:
                features = [feature['attributes'] for feature in data['features']]
                all_features.extend(features)
                
                print(f"Fetched records {offset} to {offset + len(features)} for {dataset_name}")
                
                if len(features) < chunk_size:
                    break
                    
                offset += chunk_size
            else:
                print(f"No features found in response for {dataset_name}")
                break
                
        return pd.DataFrame(all_features)
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {dataset_name}: {e}")
        return None

def save_to_azure(df, dataset_name):
    """
    Save DataFrame to Azure Blob Storage
    """
    if df is None or df.empty:
        print(f"No data to save for {dataset_name}")
        return
        
    # Create CSV in memory
    csv_buffer = BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    
    # Generate blob name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    blob_name = f"{folder_name}/{dataset_name}_{timestamp}.csv"
    
    # Upload to Azure
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(csv_buffer, overwrite=True)
        print(f"Successfully uploaded {dataset_name} to Azure")
        
        # Save data dictionary separately
        data_dict = {
            'columns': list(df.columns),
            'dtypes': df.dtypes.astype(str).to_dict(),
            'record_count': len(df),
            'timestamp': timestamp
        }
        
        dict_blob_name = f"{folder_name}/{dataset_name}_{timestamp}_dictionary.json"
        dict_blob_client = container_client.get_blob_client(dict_blob_name)
        dict_blob_client.upload_blob(json.dumps(data_dict, indent=2), overwrite=True)
        
    except Exception as e:
        print(f"Error saving {dataset_name} to Azure: {e}")
