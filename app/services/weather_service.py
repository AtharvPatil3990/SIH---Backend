import openmeteo_requests
import requests_cache
from retry_requests import retry

# 1. Setup the Open-Meteo client with caching and retries
cache_session = requests_cache.CachedSession('.cache', expire_after=1800)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

def fetch_ward_weather(lat: float, lon: float, days: int = 5, past_days: int = 2) -> dict:
    """
    Fetches weather using the official FlatBuffers SDK, calculates cumulative 
    heat stress using past days, and extracts specific timepoints.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", 
            "relative_humidity_2m", 
            "wind_speed_10m",
            "shortwave_radiation",
            "wet_bulb_temperature_2m",
            "precipitation",    
            "is_day"            
        ],
        "hourly": [
            "temperature_2m", 
            "relative_humidity_2m", 
            "wind_speed_10m", 
            "wet_bulb_temperature_2m",
            "shortwave_radiation",
            "precipitation"     
        ],
        "past_days": past_days, # 2 days of historical data
        "forecast_days": days,  # 5 days of forecast
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

    # Helper function for uniform data structure
    def get_hour_data(idx: int) -> dict:
        return {
            "temp_c": float(temp_array[idx]),
            "humidity": float(rh_array[idx]),
            "wind_speed": float(wind_array[idx]),
            "wet_bulb_c": float(wet_bulb_array[idx]),
            "solar_radiation": float(radiation_array[idx]),
            "precipitation_mm": float(precip_array[idx])
        }

    # --- 3. CUMULATIVE HEAT STRESS LOGIC ---
    WET_BULB_THRESHOLD = 26.0
    daily_2pm_wet_bulbs = []
    
    # Extract 2:00 PM wet-bulbs for ALL 7 days (2 past + 5 forecast)
    for d in range(past_days + days):
        idx = (d * 24) + 14  
        daily_2pm_wet_bulbs.append(wet_bulb_array[idx])

    forecast_list = []

    # Loop ONLY through the 5 forecast days
    for forecast_day in range(days):
        # Shift index to skip the 2 past days (Today is index 2)
        day_index = forecast_day + past_days 
        
        # Calculate lag effects
        e_t = max(0, daily_2pm_wet_bulbs[day_index] - WET_BULB_THRESHOLD)
        e_t1 = max(0, daily_2pm_wet_bulbs[day_index - 1] - WET_BULB_THRESHOLD)
        e_t2 = max(0, daily_2pm_wet_bulbs[day_index - 2] - WET_BULB_THRESHOLD)
        
        # Base Cumulative Heat Stress
        h_t = (0.5 * e_t) + (0.3 * e_t1) + (0.2 * e_t2)
        
        # Calculate indices for JSON extraction
        base_idx = day_index * 24
        min_5am_idx = base_idx + 5
        peak_2pm_idx = base_idx + 14
        evening_6pm_idx = base_idx + 18
        
        # Apply Rain Suppression Rule
        rain_2pm = float(precip_array[peak_2pm_idx])
        if rain_2pm > 2.0:
            h_t = h_t * 0.5 
        
        # Build uniform JSON block
        forecast_list.append({
            "day_offset": forecast_day,
            "night_minimum_5am": get_hour_data(min_5am_idx),
            "peak_stress_2pm": get_hour_data(peak_2pm_idx),
            "evening_retained_6pm": get_hour_data(evening_6pm_idx),
            "ml_features": {
                "cumulative_heat_stress": float(h_t)
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
            "is_day": int(current_is_day) 
        },
        "forecast": forecast_list
    }
    
    
if __name__ == "__main__":
    # Example usage
    lat = 18.52  # Latitude for New Delhi
    lon =  73.86 # Longitude for New Delhi
    weather_data = fetch_ward_weather(lat, lon)
    print(weather_data)