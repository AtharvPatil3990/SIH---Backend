import os
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import date

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
    # Uses 'census_ward_number' column which stores the UUID foreign key per your schema
    weather_res = supabase.table('weather_forecasts')\
        .select('*')\
        .eq('census_ward_number', ward_uuid)\
        .gte('forecast_date', str(date.today()))\
        .order('forecast_date')\
        .execute()
        
    if not weather_res.data:
        raise HTTPException(status_code=404, detail="Weather cache missing. Ensure cron job has run.")

    forecast_results = []
    BASE_RATE = 0.00015

    # C. Process Each Day Through the XGBoost Model
    for day in weather_res.data:
        feature_dict = {
            'ward_elderly_pct': ward_data['ward_elderly_pct'],
            'child_pct': ward_data['child_pct'],
            'slum_pct': ward_data['slum_pct'],
            'temp_c': day['temp_c'],
            'humidity': day['humidity'],
            'wind_speed': day['wind_speed'],
            'solar_radiation': day['solar_radiation'],
            'precipitation_mm': day['precipitation_mm'],
            'is_day': 1, 
            'wet_bulb_c': day['wet_bulb_c'],
            'utci_c': day['utci_c'],
            'cumul_utci_stress': day['cumul_utci_stress']
        }
        
        df_features = pd.DataFrame([feature_dict])
        risk_multiplier = float(xgb_model.predict(df_features)[0])
        expected_casualties = int((ward_data['total_population'] * BASE_RATE) * risk_multiplier)

        if expected_casualties > 10:
            alert = "RED_EMERGENCY"
        elif expected_casualties > 5:
            alert = "ORANGE_ALERT"
        elif expected_casualties > 2:
            alert = "YELLOW_WARNING"
        else:
            alert = "NORMAL"

        forecast_results.append({
            "date": day['forecast_date'],
            "utci_c": day['utci_c'],
            "risk_multiplier": round(risk_multiplier, 2),
            "estimated_admissions": expected_casualties,
            "alert_tier": alert,
            "recommended_actions": ALERT_ACTIONS[alert]
        })

    # D. Fetch Live Weather via HTTP Cache
    try:
        live_weather_payload = weather_service.fetch_ward_weather(
            lat=ward_data['latitude'], 
            lon=ward_data['longitude']
        )
        live_current = live_weather_payload['current']
    except Exception as e:
        print(f"Live weather fetch failed: {e}")
        live_current = None

    # E. Return Blended Payload
    return {
        "ward_uuid": ward_uuid,
        "city_corporation": ward_data['city_corporation'],
        "census_ward_number": ward_data['census_ward_number'],
        "ward_name": ward_data['ward_name'],
        "hvi_score": ward_data['hvi_score'],
        "total_population": ward_data['total_population'],
        "live_weather": live_current,
        "forecast": forecast_results
    }