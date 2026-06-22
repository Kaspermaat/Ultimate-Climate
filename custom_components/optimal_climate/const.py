DOMAIN = "optimal_climate"

# Zone-level config keys
CONF_ZONE_NAME = "zone_name"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_CO2_SENSOR = "co2_sensor"
CONF_HUMIDITY_INDOOR = "humidity_indoor"
CONF_HUMIDITY_OUTDOOR = "humidity_outdoor"
CONF_TEMP_OUTDOOR = "temp_outdoor"
CONF_TEMP_SENSORS = "temp_sensors"          # list of extra indoor temp sensor entity IDs
CONF_FAN_ENTITY = "fan_entity"
CONF_WINDOW_TEMP_MIN = "window_temp_min"
CONF_WINDOW_TEMP_MAX = "window_temp_max"

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
DEFAULT_WINDOW_TEMP_MAX = 26

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

# Humidity: max outdoor-indoor delta before skipping ventilation (%)
HUMIDITY_OUTDOOR_MARGIN = 10

# Fan
FAN_MIN_SPEED = 20
FAN_SUMMER_COOLING_DELTA = 2.0

# Comfort score weights (must sum to 1.0)
WEIGHT_CO2 = 0.35
WEIGHT_HUMIDITY = 0.30
WEIGHT_TEMP = 0.35
