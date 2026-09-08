import os
import time
from datetime import date, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

# Import your existing weather ingestion service
from app.services import weather_service 

# 1. Initialize Supabase Client
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials in .env file")

supabase: Client = create_client(url, key)

def update_all_wards_weather():
    print(f"Starting Daily Weather Ingestion for {date.today()}...")
    
    # 2. Fetch all wards and their coordinates from the database
    # Adjust 'census_ward_number' to 'id' (UUID) if you fully migrated to the national schema
    response = supabase.table('wards').select('census_ward_number, latitude, longitude').execute()
    wards = response.data
    
    if not wards:
        print("No wards found in the database. Exiting.")
        return

    print(f"Found {len(wards)} wards. Fetching Open-Meteo forecasts...")
    
    records_to_upsert = []
    today = date.today()

    # 3. Iterate through each ward
    for index, ward in enumerate(wards):
        ward_id = ward['census_ward_number']
        lat = ward['latitude']
        lon = ward['longitude']
        
        try:
            # Fetch the parsed data from your existing script
            weather_data = weather_service.fetch_ward_weather(lat=lat, lon=lon)
            
            # Loop through the 5 forecast days returned by the service
            for day in weather_data['forecast']:
                day_offset = day['day_offset']
                forecast_date = today + timedelta(days=day_offset)
                
                # We use the 2:00 PM peak stress block because it drives the machine learning model
                peak_metrics = day['peak_stress_2pm']
                
                # Format payload to exactly match your Supabase SQL schema
                record = {
                    "census_ward_number": ward_id,
                    "forecast_date": str(forecast_date),
                    "day_offset": day_offset,
                    "temp_c": peak_metrics['temp_c'],
                    "humidity": peak_metrics['humidity'],
                    "wind_speed": peak_metrics['wind_speed'],
                    "solar_radiation": peak_metrics['solar_radiation'],
                    "precipitation_mm": peak_metrics['precipitation_mm'],
                    "wet_bulb_c": peak_metrics['wet_bulb_c'],
                    "utci_c": peak_metrics['utci_c'],
                    "cumul_utci_stress": day['ml_features']['cumulative_heat_stress']
                }
                records_to_upsert.append(record)
            
            # Optional: Add a tiny sleep to prevent overwhelming the Open-Meteo API
            # Open-Meteo allows 10,000 calls/day, so 145 wards is well within limits, but pacing is good practice.
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"Error fetching data for Ward {ward_id}: {e}")
            continue

    # 4. Bulk Upsert into Supabase
    if records_to_upsert:
        print(f"Pushing {len(records_to_upsert)} forecast records to Supabase cache...")
        try:
            # Upsert overwrites the row if the (census_ward_number, forecast_date) combination already exists
            db_response = supabase.table('weather_forecasts').upsert(
                records_to_upsert, 
                on_conflict="census_ward_number, forecast_date"
            ).execute()
            print("Successfully updated database cache!")
        except Exception as e:
            print(f"Database insertion failed: {e}")
    else:
        print("No valid forecast data generated.")

if __name__ == "__main__":
    update_all_wards_weather()