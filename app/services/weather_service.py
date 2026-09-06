import openmeteo_requests
import requests_cache
from retry_requests import retry
from thermal_service import calculate_utci # Import your new UTCI service

# 1. Setup the Open-Meteo client with caching and retries
cache_session = requests_cache.CachedSession('.cache', expire_after=1800)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

def fetch_ward_weather(lat: float, lon: float, days: int = 5, past_days: int = 2) -> dict:
    """
    Fetches weather using the official FlatBuffers SDK, calculates UTCI via thermal_service, 
    computes cumulative UTCI heat stress using past days, and extracts specific timepoints.
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
        "past_days": past_days, 
        "forecast_days": days,  
        "wind_speed_unit": "ms",
        "timezone": "Asia/Kolkata"
    }
    
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0] 
    
    # --- 1. EXTRACT CURRENT (LIVE) DATA ---
    current = response.Current()
    current_temp = float(current.Variables(0).Value())
    current_rh = float(current.Variables(1).Value())
    current_wind = float(current.Variables(2).Value())
    current_rad = float(current.Variables(3).Value())
    current_wet_bulb = float(current.Variables(4).Value())
    current_precip = float(current.Variables(5).Value())
    current_is_day = int(current.Variables(6).Value())
    
    # Calculate Live UTCI
    current_utci = calculate_utci(
        temp_c=current_temp, 
        wind_speed_10m=current_wind, 
        humidity=current_rh, 
        solar_radiation=current_rad
    )
    
    # --- 2. EXTRACT HOURLY FORECAST DATA ---
    hourly = response.Hourly()
    temp_array = hourly.Variables(0).ValuesAsNumpy()
    rh_array = hourly.Variables(1).ValuesAsNumpy()
    wind_array = hourly.Variables(2).ValuesAsNumpy()
    wet_bulb_array = hourly.Variables(3).ValuesAsNumpy()
    radiation_array = hourly.Variables(4).ValuesAsNumpy()
    precip_array = hourly.Variables(5).ValuesAsNumpy()

    # Helper function for uniform data structure (Now includes UTCI)
    def get_hour_data(idx: int) -> dict:
        t_c = float(temp_array[idx])
        rh = float(rh_array[idx])
        wind = float(wind_array[idx])
        rad = float(radiation_array[idx])
        
        utci_val = calculate_utci(temp_c=t_c, wind_speed_10m=wind, humidity=rh, solar_radiation=rad)
        
        return {
            "temp_c": t_c,
            "humidity": rh,
            "wind_speed": wind,
            "wet_bulb_c": float(wet_bulb_array[idx]),
            "solar_radiation": rad,
            "precipitation_mm": float(precip_array[idx]),
            "utci_c": round(float(utci_val), 2)
        }

    # --- 3. CUMULATIVE HEAT STRESS LOGIC (NOW USING UTCI) ---
    UTCI_THRESHOLD = 34.0
    daily_2pm_utci = []
    
    # Extract 2:00 PM UTCI for ALL 7 days (2 past + 5 forecast) by calculating it on the fly
    for d in range(past_days + days):
        idx = (d * 24) + 14  
        t_c = float(temp_array[idx])
        rh = float(rh_array[idx])
        wind = float(wind_array[idx])
        rad = float(radiation_array[idx])
        
        day_utci = calculate_utci(temp_c=t_c, wind_speed_10m=wind, humidity=rh, solar_radiation=rad)
        daily_2pm_utci.append(day_utci.utci)

    forecast_list = []

    # Loop ONLY through the 5 forecast days
    for forecast_day in range(days):
        day_index = forecast_day + past_days 
        
        # Calculate lag effects using the calculated UTCI Array
        e_t = max(0, daily_2pm_utci[day_index] - UTCI_THRESHOLD)
        e_t1 = max(0, daily_2pm_utci[day_index - 1] - UTCI_THRESHOLD)
        e_t2 = max(0, daily_2pm_utci[day_index - 2] - UTCI_THRESHOLD)
        
        h_t = (0.5 * e_t) + (0.3 * e_t1) + (0.2 * e_t2)
        
        # Array Indices
        base_idx = day_index * 24
        min_5am_idx = base_idx + 5
        peak_2pm_idx = base_idx + 14
        evening_6pm_idx = base_idx + 18
        
        # Apply Rain Suppression Rule
        rain_2pm = float(precip_array[peak_2pm_idx])
        if rain_2pm > 2.0:
            h_t = h_t * 0.5 
        
        forecast_list.append({
            "day_offset": forecast_day,
            "night_minimum_5am": get_hour_data(min_5am_idx),
            "peak_stress_2pm": get_hour_data(peak_2pm_idx),
            "evening_retained_6pm": get_hour_data(evening_6pm_idx),
            "ml_features": {
                "cumulative_heat_stress": round(float(h_t), 2)
            }
        })

    return {
        "current": {
            "temp_c": current_temp,
            "humidity": current_rh,
            "wind_speed": current_wind,
            "wet_bulb_c": current_wet_bulb,
            "solar_radiation": current_rad,
            "precipitation_mm": current_precip,
            "is_day": current_is_day,
            "utci_c": round(float(current_utci), 2) # <-- Live UTCI for frontend display
        },
        "forecast": forecast_list
    }
    
if __name__ == "__main__":
    # Example usage
    lat = 18.52  # Latitude for New Delhi
    lon =  73.86 # Longitude for New Delhi
    weather_data = fetch_ward_weather(lat, lon)
    print(weather_data)