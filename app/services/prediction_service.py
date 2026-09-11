import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, UTC, timedelta
from app.services.weather_service import fetch_ward_weather

# Load your compiled XGBoost model
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'heat_risk_xgboost_model.pkl')
model = joblib.load(MODEL_PATH)

def calculate_ward_prediction(ward_uuid: str, supabase_client):
    """
    1. Fetches ward demographics & coordinates from Supabase.
    2. Fetches live weather via Open-Meteo.
    3. Runs XGBoost prediction with exact column ordering.
    4. Caches 5-day intervals (5am, 2pm, 6pm) in Supabase.
    """
    # 1. Get ward metadata from Supabase
    ward_res = supabase_client.table('wards').select('*').eq('id', ward_uuid).execute()
    if not ward_res.data:
        raise ValueError(f"Ward UUID {ward_uuid} not found in database.")
    
    ward = ward_res.data[0]
    lat = ward.get('latitude', 18.5204)
    lon = ward.get('longitude', 73.8567)
        
    # 2. Get live weather
    weather = fetch_ward_weather(lat=lat, lon=lon)
    current = weather['current']
    
    # 3. Construct feature array for CURRENT day
    features_current = pd.DataFrame([{
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
    
    # Run Current Prediction
    current_casualties = max(0, round(float(model.predict(features_current)[0]), 1))
    if current_casualties > 10: current_tier = "RED_ALERT"
    elif current_casualties > 5: current_tier = "ORANGE_ALERT"
    elif current_casualties > 2: current_tier = "YELLOW_ALERT"
    else: current_tier = "NORMAL"
        
    # 4. Construct feature arrays for FORECAST days
    forecast_list = []
    for day in weather['forecast']:
        # Safely extract metrics whether nested or flat
        peak_weather = day.get('peak_stress_2pm', day)
        ml_features = day.get('ml_features', day)
        
        features_forecast = pd.DataFrame([{
            'ward_elderly_pct': ward.get('ward_elderly_pct', 0.12),
            'child_pct': ward.get('child_pct', 0.12),
            'slum_pct': ward.get('slum_pct', 0.28),
            'temp_c': peak_weather.get('temp_c', 35.0),
            'humidity': peak_weather.get('humidity', 40.0),
            'wind_speed': peak_weather.get('wind_speed', 5.0),
            'solar_radiation': peak_weather.get('solar_radiation', 500.0),
            'precipitation_mm': peak_weather.get('precipitation_mm', 0.0),
            'is_day': 1,
            'wet_bulb_c': peak_weather.get('wet_bulb_c', 22.0),
            'utci_c': peak_weather.get('utci_c', 36.0),
            'cumul_utci_stress': ml_features.get('cumulative_heat_stress', 1.5),
            'total_population': ward.get('total_population', 50000)
        }])
        
        day_casualties = max(0, round(float(model.predict(features_forecast)[0]), 1))
        
        if day_casualties > 10: day_tier = "RED_EMERGENCY"
        elif day_casualties > 5: day_tier = "ORANGE_ALERT"
        elif day_casualties > 2: day_tier = "YELLOW_WARNING"
        else: day_tier = "NORMAL"
        
        forecast_list.append({
            "predicted_hospitalizations": day_casualties,
            "alert_tier": day_tier,
            "weather_snapshot": day
        })

    prediction_result = {
        "data": {
            "ward_uuid": ward_uuid,
            "ward_name": ward.get('ward_name'),
            "current": {
                "predicted_hospitalizations": current_casualties,
                "alert_tier": current_tier,
                "weather_snapshot": current
            },
            "forecast": forecast_list
        }
    }

    try:
        today_date = datetime.now(UTC).date()
        unique_records = {}
        
        # 1. Process the forecast array (This builds the 5am/2pm/6pm blocks for ALL days, including Today)
        for i, forecast_item in enumerate(forecast_list):
            target_date = (today_date + timedelta(days=i)).isoformat()
            day_weather = forecast_item["weather_snapshot"]
            
            unique_records[target_date] = {
                "ward_id": ward_uuid,
                "forecast_date": target_date,
                "weather_5am": day_weather.get("night_minimum_5am", day_weather),
                "weather_2pm": day_weather.get("peak_stress_2pm", day_weather),
                "weather_6pm": day_weather.get("evening_retained_6pm", day_weather),
                "predicted_hospitalizations": forecast_item["predicted_hospitalizations"],
                "alert_tier": forecast_item["alert_tier"],
                "temperature": day_weather.get("peak_stress_2pm", day_weather).get("temp_c", 35.0),
                "updated_at": datetime.now(UTC).isoformat()
            }
            
        # 2. TARGETED OVERWRITE: Inject the live calculated casualties into Today's record
        # This keeps the 5am/2pm/6pm blocks perfectly intact.
        today_iso = today_date.isoformat()
        if today_iso in unique_records:
            unique_records[today_iso]["predicted_hospitalizations"] = current_casualties
            unique_records[today_iso]["alert_tier"] = current_tier
        else:
            # Fallback in case Open-Meteo's forecast array started on tomorrow
            unique_records[today_iso] = {
                "ward_id": ward_uuid,
                "forecast_date": today_iso,
                "weather_5am": current, 
                "weather_2pm": current, 
                "weather_6pm": current, 
                "predicted_hospitalizations": current_casualties,
                "alert_tier": current_tier,
                "temperature": current.get("temp_c", 35.0),
                "updated_at": datetime.now(UTC).isoformat()
            }
        
        # 3. Convert to list and execute single bulk database write
        cache_records = list(unique_records.values())
        
        supabase_client.table('weather_cache').upsert(
            cache_records, 
            on_conflict="ward_id,forecast_date"
        ).execute()
        print(f"Successfully cached {len(cache_records)} days for ward {ward_uuid}")
        
    except Exception as e:
        print(f"Background cache update failed (non-fatal): {e}")

    return prediction_result