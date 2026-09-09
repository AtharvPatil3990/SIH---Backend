import os
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import date
from app.services.weather_service import fetch_ward_weather
from app.services.prediction_service import calculate_ward_prediction

# Import your HTTP-cached weather service
from app.services import weather_service

# 1. Initialize Application & CORS
app = FastAPI(title="Heat-Health Risk Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Load Environment Variables & External Clients
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
if not url or not key:
    raise RuntimeError("Supabase credentials missing from .env")

supabase: Client = create_client(url, key)

# 3. Load Machine Learning Model into Memory
try:
    model_path = os.path.join(os.path.dirname(__file__), '..', 'heat_risk_xgboost_model.pkl')
    xgb_model = joblib.load(model_path)
    print("XGBoost Model loaded successfully.")
except Exception as e:
    print(f"Warning: Model file not found. {e}")
    xgb_model = None

# 4. Define Public Health Interventions
ALERT_ACTIONS = {
    "NORMAL": [
        "No extreme heat risks today. Enjoy outdoor activities safely.",
        "Maintain your standard daily water intake."
    ],
    "YELLOW_WARNING": [
        "Drink water regularly, even if you do not feel thirsty.",
        "Try to limit strenuous outdoor exercise between 12:00 PM and 4:00 PM.",
        "Wear lightweight, light-colored clothing if going outside."
    ],
    "ORANGE_ALERT": [
        "Avoid going outdoors during peak afternoon hours (12:00 PM - 4:00 PM).",
        "Stay in shaded, well-ventilated, or air-conditioned spaces.",
        "Check on elderly family members and young children frequently."
    ],
    "RED_EMERGENCY": [
        "Severe heat emergency. Stay indoors at all times if possible.",
        "Strictly avoid any outdoor physical labor or exercise today.",
        "Drink ORS or electrolytes continuously and seek immediate medical help for dizziness."
    ]
}

# --- API ENDPOINTS ---

@app.get("/api/wards")
def get_all_wards():
    """Provides the React map with base HVI scores and the UUID to render the initial color map."""
    # Added 'id' and hierarchy columns so the frontend knows the UUID to query
    response = supabase.table('wards').select(
        'id, district, city_corporation, census_ward_number, ward_name, latitude, longitude, hvi_score'
    ).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="No wards found in database")
    return response.data

@app.get("/api/predict/{ward_uuid}")
def get_ward_prediction(ward_uuid: str): # <-- Changed to str to accept UUID
    """Executes the ML model and returns the projected casualty timeline and live weather."""
    if xgb_model is None:
        raise HTTPException(status_code=500, detail="ML Model not loaded on server.")

    # A. Fetch Static Demographics using the UUID
    ward_res = supabase.table('wards').select('*').eq('id', ward_uuid).execute()
    if not ward_res.data:
        raise HTTPException(status_code=404, detail="Ward UUID not found.")
    ward_data = ward_res.data[0]

    # B. Fetch Cached 7-Day Weather Forecast
    # weather_res = calculate_ward_prediction(ward_uuid, supabase)
        
    # return weather_res
    weather_res = supabase.table('weather_cache')\
        .select('*')\
        .eq('ward_id', ward_uuid)\
        .gte('forecast_date', str(date.today()))\
        .order('forecast_date')\
        .execute()

    # Null Check: Repackage and return if all 5 days exist
    if weather_res.data and len(weather_res.data) >= 5:
        db_rows = weather_res.data
        
        formatted_forecast = []
        for row in db_rows:
            formatted_forecast.append({
                "predicted_hospitalizations": row["predicted_hospitalizations"],
                "alert_tier": row["alert_tier"],
                "weather_snapshot": {
                    "night_minimum_5am": row["weather_5am"],
                    "peak_stress_2pm": row["weather_2pm"],
                    "evening_retained_6pm": row["weather_6pm"]
                }
            })

        return {
            "source": "database_cache",
            "data": {
                "ward_uuid": ward_uuid,
                "current": {
                    "predicted_hospitalizations": db_rows[0]["predicted_hospitalizations"],
                    "alert_tier": db_rows[0]["alert_tier"],
                    "weather_snapshot": {
                        "night_minimum_5am": db_rows[0]["weather_5am"],
                        "peak_stress_2pm": db_rows[0]["weather_2pm"],
                        "evening_retained_6pm": db_rows[0]["weather_6pm"]
                    }
                },
                "forecast": formatted_forecast
            }
        }

    # 2. FALLBACK: Cache was empty, pass control to prediction service
    print("Cache miss! Calculating live predictions...")
    return calculate_ward_prediction(ward_uuid, supabase)