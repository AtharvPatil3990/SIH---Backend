import openmeteo_requests
import requests_cache
from retry_requests import retry

# 1. Setup the Open-Meteo client with caching and retries
# This caches responses for 1 hour (3600 seconds) to save API calls
cache_session = requests_cache.CachedSession('.cache', expire_after=1800)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

def fetch_ward_weather(lat: float, lon: float, days: int = 5) -> dict:
    """
    Fetches weather using the official FlatBuffers SDK and extracts 2:00 PM data.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    
    # 2. Define exactly what your early warning system needs       
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", 
            "relative_humidity_2m", 
            "wind_speed_10m",
            "shortwave_radiation",
            "wet_bulb_temperature_2m",  # <-- ADDED: Live wet bulb check
            "precipitation",    # <-- ADDED: Live rain check
            "is_day"            # <-- ADDED: 1 for Day, 0 for Night (for UI icons)
        ],
        "hourly": [
            "temperature_2m", 
            "relative_humidity_2m", 
            "wind_speed_10m", 
            "wet_bulb_temperature_2m",
            "shortwave_radiation",
            "precipitation"     # <-- ADDED: Hourly rain check
        ],
        "forecast_days": days,
        "wind_speed_unit": "ms",
        "timezone": "Asia/Kolkata"
    }
    
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0] 
    
    # --- 1. EXTRACT CURRENT (LIVE) DATA ---
    current = response.Current()
    current_temp = current.Variables(0).Value()
    current_rh = current.Variables(1).Value()
    current_wind = current.Variables(2).Value()
    current_rad = current.Variables(3).Value()
    current_wet_bulb = current.Variables(4).Value()
    current_precip = current.Variables(5).Value()
    current_is_day = current.Variables(6).Value()
    
    
    # --- 2. EXTRACT HOURLY FORECAST DATA ---
    hourly = response.Hourly()
    temp_array = hourly.Variables(0).ValuesAsNumpy()
    rh_array = hourly.Variables(1).ValuesAsNumpy()
    wind_array = hourly.Variables(2).ValuesAsNumpy()
    wet_bulb_array = hourly.Variables(3).ValuesAsNumpy()
    radiation_array = hourly.Variables(4).ValuesAsNumpy()
    precip_array = hourly.Variables(5).ValuesAsNumpy()

    forecast_list = []

    for day in range(days):
        base_idx = day * 24
        min_5am_idx = base_idx + 5
        peak_2pm_idx = base_idx + 14
        evening_6pm_idx = base_idx + 18
        
        forecast_list.append({
            "day_offset": day,
            "night_minimum_5am": {
                "temp_c": float(temp_array[min_5am_idx]),
                "humidity": float(rh_array[min_5am_idx]),
                "wind_speed": float(wind_array[min_5am_idx]),
                "wet_bulb_c": float(wet_bulb_array[min_5am_idx]),
                "solar_radiation": float(radiation_array[min_5am_idx]),
                "precipitation_mm": float(precip_array[min_5am_idx])
            },
            
            "peak_stress_2pm": {
                "temp_c": float(temp_array[peak_2pm_idx]),
                "humidity": float(rh_array[peak_2pm_idx]),
                "wind_speed": float(wind_array[peak_2pm_idx]),
                "wet_bulb_c": float(wet_bulb_array[peak_2pm_idx]),
                "solar_radiation": float(radiation_array[peak_2pm_idx]),
                "precipitation_mm": float(precip_array[peak_2pm_idx]) # <-- Sent to Risk Engine
            },
            "evening_retained_6pm": {
                "temp_c": float(temp_array[evening_6pm_idx]),
                "humidity": float(rh_array[evening_6pm_idx]),
                "wind_speed": float(wind_array[evening_6pm_idx]),
                "wet_bulb_c": float(wet_bulb_array[evening_6pm_idx]),
                "solar_radiation": float(radiation_array[evening_6pm_idx]),
                "precipitation_mm": float(precip_array[evening_6pm_idx])
            }
        })

    return {
        "current": {
            "temp_c": float(current_temp),
            "humidity": float(current_rh),
            "wind_speed": float(current_wind),
            "wet_bulb_c": float(current_wet_bulb),
            "solar_radiation": float(current_rad),
            "precipitation_mm": float(current_precip),
            "is_day": int(current_is_day)  # 1 = Day, 0 = Night
        },
        "forecast": forecast_list
    }
