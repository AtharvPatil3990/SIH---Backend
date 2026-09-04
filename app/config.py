from pydantic_settings import BaseSettings
from typing import Dict, Any

from pydantic_settings import BaseSettings
from typing import Dict, Any

# 1. Environment Variables & Secrets
class Settings(BaseSettings):
    PROJECT_NAME: str = "Extreme Heatwave Early Warning System"
    VERSION: str = "1.0.0"
    
    # Supabase Credentials (Required)
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    class Config:
        env_file = ".env"  # Tells Pydantic to read from your .env file

# Instantiate the settings so other files can import it
settings = Settings()

# 2. Ward Metadata & Vulnerability Multipliers
# The keys (1, 2, 3...) must match exactly with the "wardnum" property in your pune-2022-wards.geojson file.
# WARDS_METADATA: Dict[int, Dict[str, Any]] = {
#     1: {
#         "name": "Dhanori - Vishrantwadi", 
#         "lat": 18.6012, 
#         "lon": 73.9077, 
#         "elderly_pct": 0.18,   # 18% elderly
#         "outdoor_pct": 0.35,   # 35% outdoor/construction workers
#         "slum_pct": 0.20       # 20% informal settlements
#     },
#     2: {
#         "name": "Tingrenagar - Sanjay Park", 
#         "lat": 18.5920, 
#         "lon": 73.9117, 
#         "elderly_pct": 0.25,   # Aging neighborhood
#         "outdoor_pct": 0.10, 
#         "slum_pct": 0.05
#     },
#     3: {
#         "name": "Lohegaon - Vimannagar", 
#         "lat": 18.6204, 
#         "lon": 73.9305, 
#         "elderly_pct": 0.12, 
#         "outdoor_pct": 0.45,   # High construction zone
#         "slum_pct": 0.15
#     },
#     4: {
#         "name": "East Kharadi - Wagholi", 
#         "lat": 18.6040, 
#         "lon": 74.0104, 
#         "elderly_pct": 0.10, 
#         "outdoor_pct": 0.50, 
#         "slum_pct": 0.30       # High density labor camps
#     },
#     5: {
#         "name": "West Kharadi - Vadgaon Sheri", 
#         "lat": 18.5636, 
#         "lon": 73.9344, 
#         "elderly_pct": 0.15, 
#         "outdoor_pct": 0.25, 
#         "slum_pct": 0.40       # High slum density
#     }
# }