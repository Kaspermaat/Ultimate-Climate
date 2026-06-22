DOMAIN = "optimal_climate"

# Config entry keys
CONF_ZONE_NAME = "zone_name"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_CO2_SENSOR = "co2_sensor"
CONF_HUMIDITY_INDOOR = "humidity_indoor"
CONF_HUMIDITY_OUTDOOR = "humidity_outdoor"
CONF_TEMP_OUTDOOR = "temp_outdoor"
CONF_COVER_ENTITIES = "cover_entities"
CONF_WINDOW_ENTITIES = "window_entities"
CONF_FAN_ENTITY = "fan_entity"
CONF_WINDOW_AZIMUTH = "window_azimuth"         # compass degrees window faces (0-359)
CONF_WINDOW_FOV = "window_fov"                 # half-angle of window view cone (degrees)
CONF_WINDOW_TEMP_MIN = "window_temp_min"       # min outdoor °C to allow opening
CONF_WINDOW_TEMP_MAX = "window_temp_max"       # max outdoor °C to allow opening
CONF_WINDOW_CURTAIN_MAP = "window_curtain_map" # dict: window_entity_id → curtain_entity_id
CONF_CURTAIN_MIN_OPEN = "curtain_min_open"     # % curtain must stay open when window is open

# Platforms enabled by this integration
PLATFORMS = ["sensor", "select"]

# Modes
MODE_AUTO = "auto"
MODE_MANUAL = "handmatig"
MODE_AWAY = "afwezig"
MODE_SLEEP = "slaap"

# Cover defaults
DEFAULT_WINDOW_AZIMUTH = 180    # south-facing
DEFAULT_WINDOW_FOV = 90         # ±90° view cone
COVER_HYSTERESIS = 3            # only move cover if position shifts > 3%

# Window temperature gate defaults (°C)
DEFAULT_WINDOW_TEMP_MIN = 14
DEFAULT_WINDOW_TEMP_MAX = 26

# Minimum curtain opening (%) when paired window is open
DEFAULT_CURTAIN_MIN_OPEN = 10

# Services
SERVICE_RECALCULATE = "recalculate"

# Polling interval in seconds
DEFAULT_SCAN_INTERVAL = 30

# CO2 thresholds (ppm)
CO2_GOOD = 800
CO2_MODERATE = 1000
CO2_POOR = 1200

# Humidity: max outdoor-indoor delta before skipping ventilation (%)
HUMIDITY_OUTDOOR_MARGIN = 10

# Fan: minimum speed when no reason to boost (%)
FAN_MIN_SPEED = 20
# Fan: how much cooler outdoor must be vs indoor to trigger summer cooling (°C)
FAN_SUMMER_COOLING_DELTA = 2.0

# Comfort score weights (must sum to 1.0)
WEIGHT_CO2 = 0.35
WEIGHT_HUMIDITY = 0.30
WEIGHT_TEMP = 0.35
