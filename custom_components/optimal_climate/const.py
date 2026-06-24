DOMAIN = "optimal_climate"

# Zone-level config keys
CONF_ZONE_NAME = "zone_name"
CONF_CLIMATE_ENTITY = "climate_entity"       # legacy single-entity (kept for migration)
CONF_CLIMATE_CONFIGS = "climate_configs"     # list[dict] — one entry per climate device
CONF_CO2_SENSOR = "co2_sensor"
CONF_HUMIDITY_INDOOR = "humidity_indoor"
CONF_HUMIDITY_OUTDOOR = "humidity_outdoor"
CONF_TEMP_OUTDOOR = "temp_outdoor"
CONF_TEMP_SENSORS = "temp_sensors"          # list of extra indoor temp sensor entity IDs
CONF_FAN_ENTITY = "fan_entity"
CONF_WINDOW_TEMP_MIN = "window_temp_min"
CONF_WINDOW_TEMP_MAX = "window_temp_max"

# Per-climate config: stored as CONF_CLIMATE_CONFIGS = list of dicts
CONF_CLIMATE_CONFIGS = "climate_configs"

# Keys inside each climate-config dict
CC_CLIMATE_ENTITY = "entity_id"
CC_CLIMATE_TYPE = "climate_type"      # CLIMATE_TYPE_* below
CC_CLIMATE_NAME = "name"              # optional display label

# Climate types
CLIMATE_TYPE_HEATING = "verwarming"
CLIMATE_TYPE_COOLING = "koeling"
CLIMATE_TYPE_HEAT_COOL = "verwarming_koeling"

# Per-cover config: stored as CONF_COVER_CONFIGS = list of dicts
CONF_COVER_CONFIGS = "cover_configs"

# Keys inside each cover-config dict
CC_ENTITY_ID = "entity_id"
CC_NAME = "name"
CC_TYPE = "cover_type"              # COVER_TYPE_* below
CC_AZIMUTH = "azimuth"             # compass degrees (0-359) the cover faces
CC_FOV = "fov"                     # half-angle of view cone (degrees)
CC_MIN_POSITION = "min_position"   # floor: cover never goes below this % open
CC_SUN_PROTECTION = "sun_protection"
CC_ILLUMINANCE_SENSOR = "illuminance_sensor"
CC_ILLUMINANCE_THRESHOLD = "illuminance_threshold"  # lux
CC_TEMP_SENSOR = "temp_sensor"     # optional per-cover temp sensor
CC_LINKED_CURTAIN = "linked_curtain"
CC_CURTAIN_MIN_OPEN = "curtain_min_open"

# Cover types
COVER_TYPE_SHUTTER = "shutter"
COVER_TYPE_CURTAIN = "gordijn"
COVER_TYPE_WINDOW = "raam"

# Cover defaults
COVER_HYSTERESIS = 3
DEFAULT_FOV = 90
DEFAULT_ILLUMINANCE_THRESHOLD = 10000   # lux
DEFAULT_MIN_POSITION_SHUTTER = 0        # shutters may fully close
DEFAULT_MIN_POSITION_CURTAIN = 10       # curtains stay ≥ 10% open
DEFAULT_MIN_POSITION_WINDOW = 0

# Window temperature gate defaults (°C)
DEFAULT_WINDOW_TEMP_MIN = 14
DEFAULT_WINDOW_TEMP_MAX = 26  # legacy: niet meer gebruikt als absolute bovengrens

# Configureerbare raam-posities voor speciale modi
CONF_WINDOW_AWAY_POSITION = "window_away_position"
CONF_WINDOW_SLEEP_POSITION = "window_sleep_position"
CONF_WINDOW_RAIN_POSITION = "window_rain_position"
DEFAULT_WINDOW_AWAY_POSITION = 0   # % open bij afwezig (0 = dicht)
DEFAULT_WINDOW_SLEEP_POSITION = 0  # % open bij slaap
DEFAULT_WINDOW_RAIN_POSITION = 0   # % open bij regen (normaal altijd 0)

# Platforms enabled by this integration
PLATFORMS = ["sensor", "select"]

# Modes
MODE_AUTO = "auto"
MODE_MANUAL = "handmatig"
MODE_AWAY = "afwezig"
MODE_SLEEP = "slaap"

# Services
SERVICE_RECALCULATE = "recalculate"

# Polling interval in seconds
DEFAULT_SCAN_INTERVAL = 30

# CO2 thresholds (ppm)
CO2_GOOD = 800
CO2_MODERATE = 1000
CO2_POOR = 1200

# Weather — auto-detected, Buienradar preferred (geen API-key nodig)
WEATHER_ENTITY_CANDIDATES = [
    "weather.buienradar",
    "weather.home",
    "weather.forecast_home",
]
WEATHER_RAIN_CONDITIONS = frozenset({
    "rainy", "pouring", "lightning-rainy", "hail", "snowy-rainy",
})
WEATHER_WIND_CONDITIONS = frozenset({"windy", "windy-variant"})
WIND_SPEED_MAX_WINDOW = 40      # km/h — boven deze waarde gaan ramen dicht
CLOUD_COVERAGE_NO_SUN = 85      # % bewolking — boven deze waarde geen zonwering nodig

# Humidity: max outdoor-indoor delta before skipping ventilation (%)
HUMIDITY_OUTDOOR_MARGIN = 10

# Fan
FAN_MIN_SPEED = 20
FAN_SUMMER_COOLING_DELTA = 2.0

# Comfort score weights (must sum to 1.0)
WEIGHT_CO2 = 0.35
WEIGHT_HUMIDITY = 0.30
WEIGHT_TEMP = 0.35
