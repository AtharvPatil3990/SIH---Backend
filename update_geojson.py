import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv, find_dotenv

# 1. Load Supabase credentials
load_dotenv(find_dotenv())
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise RuntimeError("Supabase credentials missing from .env file.")

supabase = create_client(url, key)

def inject_uuids_into_geojson():
    print("Fetching wards and their UUIDs from Supabase...")
    
    # Fetch all rows from the 'wards' table containing 'id' and 'census_ward_number'
    response = supabase.table('wards').select('id, census_ward_number').execute()
    ward_rows = response.data
    
    # Create a lookup mapping dictionary: {census_ward_number: uuid}
    uuid_map = {row['census_ward_number']: row['id'] for row in ward_rows}
    print(f"Fetched {len(uuid_map)} ward UUIDs from Supabase.")

    # Locate the local GeoJSON file
    geojson_path = 'wards_pune.geojson' # Adjust path if it's inside a folder
    if not os.path.exists(geojson_path):
        geojson_path = 'app/wards/wards_pune.geojson'

    print(f"Loading GeoJSON from {geojson_path}...")
    with open(geojson_path, 'r') as f:
        geojson_data = json.load(f)

    updated_count = 0
    
    # Iterate through features and inject the UUID
    for feature in geojson_data['features']:
        props = feature['properties']
        raw_ward_num = props.get('wardnum')
        
        if raw_ward_num is not None:
            ward_num = int(str(raw_ward_num).split('_')[0])
            if ward_num in uuid_map:
                # Inject the Supabase primary key UUID into properties
                props['ward_uuid'] = uuid_map[ward_num]
                updated_count += 1

    # Save out the enriched GeoJSON file
    output_path = 'public/pune_wards.geojson' # Save directly to React public folder
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(geojson_data, f, indent=2)

    print(f"Success! Injected UUIDs into {updated_count} features.")
    print(f"Enriched map file saved directly to '{output_path}' for your frontend.")

if __name__ == "__main__":
    inject_uuids_into_geojson()