import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, UTC
from app.services.weather_service import fetch_ward_weather

# Load your compiled XGBoost model
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'heat_risk_xgboost_model.pkl')
model = joblib.load(MODEL_PATH)

def calculate_ward_prediction(ward_uuid: str, supabase_client):
    """
    1. Fetches ward demographics & coordinates from Supabase.
    2. Fetches live weather via Open-Meteo.
    3. Runs XGBoost prediction with exact column ordering.
    4. Caches result in Supabase for future requests.
    """
    # 1. Get ward metadata from Supabase
    ward_res = supabase_client.table('wards').select('*').eq('id', ward_uuid).execute()
    if not ward_res.data:
        raise ValueError(f"Ward UUID {ward_uuid} not found in database.")
    
    ward = ward_res.data[0]
    lat = ward.get('latitude', 18.5204)
    lon = ward.get('longitude', 73.8567)
    
    print(f"Latitude: {lat}, Longitude: {lon}")
    # 2. Get live weather
    weather = fetch_ward_weather(lat=lat, lon=lon)
    current = weather['current']
    
    # 3. Construct feature array matching training schema and column order exactly:
    # ['ward_elderly_pct', 'child_pct', 'slum_pct', 'temp_c', 'humidity', 
    #  'wind_speed', 'solar_radiation', 'precipitation_mm', 'is_day', 
    #  'wet_bulb_c', 'utci_c', 'cumul_utci_stress', 'total_population']
    features = pd.DataFrame([{
        'ward_elderly_pct': ward.get('ward_elderly_pct', 0.12),
        'child_pct': ward.get('child_pct', 0.12),
        'slum_pct': ward.get('slum_pct', 0.28),
        'temp_c': current.get('temp_c', 35.0),
        'humidity': current.get('humidity', 40.0),
        'wind_speed': current.get('wind_speed', 5.0),
        'solar_radiation': current.get('solar_radiation', 500.0),
        'precipitation_mm': current.get('precipitation_mm', 0.0),
        'is_day': current.get('is_day', 1),
        'wet_bulb_c': current.get('wet_bulb_c', 22.0),
        'utci_c': current.get('utci_c', 36.0),
        'cumul_utci_stress': current.get('cumul_utci_stress', 1.5),
        'total_population': ward.get('total_population', 50000)
    }])
    
    # 4. Run Model Prediction
    predicted_casualties = float(model.predict(features)[0])
    predicted_casualties = max(0, round(predicted_casualties, 1))
    
    # Determine Alert Tier
    if predicted_casualties > 10: 
        tier = "RED_EMERGENCY"
    elif predicted_casualties > 5: 
        tier = "ORANGE_ALERT"
    elif predicted_casualties > 2: 
        tier = "YELLOW_WARNING"
    else: 
        tier = "NORMAL"
        
    
    forecast_list = [
        
    ]
    for day in weather['forecast']:
        features = pd.DataFrame([{
            'ward_elderly_pct': ward.get('ward_elderly_pct', 0.12),
            'child_pct': ward.get('child_pct', 0.12),
            'slum_pct': ward.get('slum_pct', 0.28),
            'temp_c': day.get('temp_c', 35.0),
            'humidity': day.get('humidity', 40.0),
            'wind_speed': day.get('wind_speed', 5.0),
            'solar_radiation': day.get('solar_radiation', 500.0),
            'precipitation_mm': day.get('precipitation_mm', 0.0),
            'is_day': day.get('is_day', 1),
            'wet_bulb_c': day.get('wet_bulb_c', 22.0),
            'utci_c': day.get('utci_c', 36.0),
            'cumul_utci_stress': day.get('cumul_utci_stress', 1.5),
            'total_population': ward.get('total_population', 50000)
        }])
        
        predicted_casualties = float(model.predict(features)[0])
        predicted_casualties = max(0, round(predicted_casualties, 1))
    
    # Determine Alert Tier
        if predicted_casualties > 10: 
            tier = "RED_EMERGENCY"
        elif predicted_casualties > 5: 
            tier = "ORANGE_ALERT"
        elif predicted_casualties > 2: 
            tier = "YELLOW_WARNING"
        else: 
            tier = "NORMAL"
        
        forecast_list.append(
            {"predicted_hospitalizations": predicted_casualties,
            "alert_tier": tier,
            "weather_snapshot": day}
        )

    prediction_result = {
        "data": {
            "ward_uuid": ward_uuid,
            "ward_name": ward.get('ward_name'),
            "current":{
                "predicted_hospitalizations": predicted_casualties,
                "alert_tier": tier,
                "weather_snapshot": weather['current']
            },
            "forecast": forecast_list
        }
    }

    # 5. Background Cache Backfill to Supabase
    try:
        supabase_client.table('weather_cache').upsert({
            "ward_id": ward_uuid,
            "forecast_date": datetime.now(UTC).date(),
            "predicted_hospitalizations": predicted_casualties,
            "alert_tier": tier,
            "temperature": current['temp_c']
        }, on_conflict="ward_id,date").execute()
    except Exception as e:
        print(f"Background cache update failed (non-fatal): {e}")

    return prediction_result