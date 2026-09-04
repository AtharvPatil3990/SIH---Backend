from pythermalcomfort.models import utci

def calculate_tmrt(temp_c: float, solar_radiation_w_m2: float) -> float:
    """
    Calculates Mean Radiant Temperature (Tmrt) using the correct 
    Stefan-Boltzmann radiation balance for a standing human.
    """
    # Physics Constants
    sigma = 5.67e-8   # Stefan-Boltzmann constant (W/m^2.K^4)
    alpha = 0.70      # Shortwave absorptivity (human clothing/skin)
    epsilon = 0.97    # Longwave emissivity of the human body
    f_p = 0.25        # Solar projection factor (standing vertical cylinder)
    
    t_air_kelvin = temp_c + 273.15
    
    # shortwave flux is divided by (epsilon * sigma)
    shortwave_term = (alpha * f_p * solar_radiation_w_m2) / (epsilon * sigma)
    
    # Combine the fourth-power terms
    tmrt_kelvin = (t_air_kelvin ** 4 + shortwave_term) ** 0.25
    
    return tmrt_kelvin - 273.15

def calculate_utci(temp_c: float, wind_speed_10m: float, humidity: float, solar_radiation: float) -> float:
    """
    Calculate the Universal Thermal Climate Index (UTCI) based on temperature, wind speed, and relative humidity.
    
    Parameters:
    - temp: Temperature in degrees Celsius
    - wind_speed: Wind speed in m/s
    - rh: Relative humidity in percentage
    - tmrt: Mean Radiant Temperature in degrees Celsius
    
    Returns:
    - UTCI value in degrees Celsius
    """
    
    tmrt = calculate_tmrt(temp_c = temp_c, solar_radiation_w_m2 = solar_radiation)
    
    try:
        result = utci(tdb = temp_c, tr = tmrt, v = wind_speed_10m, rh = humidity)
        return result
    
    except Exception as e:
        print(f"UTCI calculation error: {e}")
        # Fallback to standard temperature if parameters are out of formula bounds
        return float(temp_c)
