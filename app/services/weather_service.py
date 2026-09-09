import openmeteo_requests
import requests_cache
from retry_requests import retry
from app.services.thermal_service import calculate_utci 

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
    current_utci_obj = calculate_utci(
        temp_c=current_temp, 
        wind_speed_10m=current_wind, 
        humidity=current_rh, 
        solar_radiation=current_rad
    )
    current_utci = float(current_utci_obj.utci)
    
    # --- 2. EXTRACT HOURLY FORECAST DATA ---
    hourly = response.Hourly()
    temp_array = hourly.Variables(0).ValuesAsNumpy()
    rh_array = hourly.Variables(1).ValuesAsNumpy()
    wind_array = hourly.Variables(2).ValuesAsNumpy()
    wet_bulb_array = hourly.Variables(3).ValuesAsNumpy()
    radiation_array = hourly.Variables(4).ValuesAsNumpy()
    precip_array = hourly.Variables(5).ValuesAsNumpy()

    def get_hour_data(idx: int) -> dict:
        t_c = float(temp_array[idx])
        rh = float(rh_array[idx])
        wind = float(wind_array[idx])
        rad = float(radiation_array[idx])
        
        utci_val = calculate_utci(temp_c=t_c, wind_speed_10m=wind, humidity=rh, solar_radiation=rad).utci
        
        return {
            "temp_c": t_c,
            "humidity": rh,
            "wind_speed": wind,
            "wet_bulb_c": float(wet_bulb_array[idx]),
            "solar_radiation": rad,
            "precipitation_mm": float(precip_array[idx]),
            "utci_c": round(float(utci_val), 2)
        }

    # --- 3. CUMULATIVE HEAT STRESS LOGIC ---
    UTCI_THRESHOLD = 34.0
    daily_2pm_utci = []
    
    # Extract 2:00 PM UTCI for ALL 7 days (2 past + 5 forecast)
    for d in range(past_days + days):
        idx = (d * 24) + 14  
        t_c = float(temp_array[idx])
        rh = float(rh_array[idx])
        wind = float(wind_array[idx])
        rad = float(radiation_array[idx])
        
        day_utci = calculate_utci(temp_c=t_c, wind_speed_10m=wind, humidity=rh, solar_radiation=rad).utci
        daily_2pm_utci.append(day_utci)

    # --- 4. CALCULATE LIVE CUMULATIVE STRESS (FOR CURRENT/ON-DEMAND) ---
    e_current = max(0, current_utci - UTCI_THRESHOLD)
    e_yesterday = max(0, daily_2pm_utci[past_days - 1] - UTCI_THRESHOLD)
    e_day_before = max(0, daily_2pm_utci[past_days - 2] - UTCI_THRESHOLD)
    
    current_cumul_stress = (0.5 * e_current) + (0.3 * e_yesterday) + (0.2 * e_day_before)
    
    # Rain suppression rule for current conditions
    if current_precip > 2.0:
        current_cumul_stress *= 0.5

    # --- 5. CALCULATE FORECAST CUMULATIVE STRESS ---
    forecast_list = []
    for forecast_day in range(days):
        day_index = forecast_day + past_days 
        
        e_t = max(0, daily_2pm_utci[day_index] - UTCI_THRESHOLD)
        e_t1 = max(0, daily_2pm_utci[day_index - 1] - UTCI_THRESHOLD)
        e_t2 = max(0, daily_2pm_utci[day_index - 2] - UTCI_THRESHOLD)
        
        h_t = (0.5 * e_t) + (0.3 * e_t1) + (0.2 * e_t2)
        
        base_idx = day_index * 24
        min_5am_idx = base_idx + 5
        peak_2pm_idx = base_idx + 14
        evening_6pm_idx = base_idx + 18
        
        rain_2pm = float(precip_array[peak_2pm_idx])
        if rain_2pm > 2.0:
            h_t *= 0.5 
        
        forecast_list.append({
            "day_offset": forecast_day,
            "night_minimum_5am": get_hour_data(min_5am_idx),
            "peak_stress_2pm": get_hour_data(peak_2pm_idx),
            "evening_retained_6pm": get_hour_data(evening_6pm_idx),
            "cumulative_heat_stress": round(float(h_t), 2)
            
        })

    return {
        "current": {
            "temp_c": round(current_temp, 2),
            "humidity": round(current_rh, 2),
            "wind_speed": round(current_wind, 2),
            "wet_bulb_c": round(current_wet_bulb, 2),
            "solar_radiation": round(current_rad, 2),
            "precipitation_mm": round(current_precip, 2),
            "is_day": current_is_day,
            "utci_c": round(current_utci, 2),
            "cumulative_heat_stress": round(float(current_cumul_stress), 2) 
        },
        "forecast": forecast_list
    }