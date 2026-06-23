"""Config flow: zone → klimaat (één voor één) → sensoren → covers → afronden."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CC_AZIMUTH,
    CC_CLIMATE_ENTITY,
    CC_CLIMATE_NAME,
    CC_CLIMATE_TYPE,
    CC_CURTAIN_MIN_OPEN,
    CC_ENTITY_ID,
    CC_FOV,
    CC_ILLUMINANCE_SENSOR,
    CC_ILLUMINANCE_THRESHOLD,
    CC_LINKED_CURTAIN,
    CC_MIN_POSITION,
    CC_NAME,
    CC_SUN_PROTECTION,
    CC_TEMP_SENSOR,
    CC_TYPE,
    CLIMATE_TYPE_COOLING,
    CLIMATE_TYPE_HEAT_COOL,
    CLIMATE_TYPE_HEATING,
    CONF_CLIMATE_CONFIGS,
    CONF_CO2_SENSOR,
    CONF_COVER_CONFIGS,
    CONF_FAN_ENTITY,
    CONF_HUMIDITY_INDOOR,
    CONF_HUMIDITY_OUTDOOR,
    CONF_TEMP_OUTDOOR,
    CONF_TEMP_SENSORS,
    CONF_WINDOW_TEMP_MAX,
    CONF_WINDOW_TEMP_MIN,
    CONF_ZONE_NAME,
    COVER_TYPE_CURTAIN,
    COVER_TYPE_SHUTTER,
    COVER_TYPE_WINDOW,
    DEFAULT_FOV,
    DEFAULT_ILLUMINANCE_THRESHOLD,
    DEFAULT_MIN_POSITION_CURTAIN,
    DEFAULT_MIN_POSITION_SHUTTER,
    DEFAULT_MIN_POSITION_WINDOW,
    DEFAULT_WINDOW_TEMP_MAX,
    DEFAULT_WINDOW_TEMP_MIN,
    DOMAIN,
)


class OptimalClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    @staticmethod
    def async_get_options_flow(config_entry):
        return OptimalClimateOptionsFlow(config_entry)

    # ------------------------------------------------------------------
    # Stap 1: alleen de zonenaam
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data[CONF_ZONE_NAME] = user_input[CONF_ZONE_NAME]
            return await self.async_step_climate_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ZONE_NAME, default="Woonkamer"): str,
            }),
        )

    # ------------------------------------------------------------------
    # Stap 2: klimaat-apparaten (menu)
    # ------------------------------------------------------------------

    async def async_step_climate_menu(self, user_input=None):
        count = len(self._data.get(CONF_CLIMATE_CONFIGS) or [])
        return self.async_show_menu(
            step_id="climate_menu",
            menu_options=["add_climate", "climate_done"],
            description_placeholders={"count": str(count)},
        )

    async def async_step_add_climate(self, user_input=None):
        if user_input is not None:
            configs = self._data.setdefault(CONF_CLIMATE_CONFIGS, [])
            configs.append({k: v for k, v in user_input.items() if v not in (None, "")})
            return await self.async_step_climate_menu()

        return self.async_show_form(
            step_id="add_climate",
            data_schema=_climate_schema(),
        )

    async def async_step_climate_done(self, user_input=None):
        return await self.async_step_sensors()

    # ------------------------------------------------------------------
    # Stap 3: sensoren
    # ------------------------------------------------------------------

    async def async_step_sensors(self, user_input=None):
        if user_input is not None:
            self._data.update({k: v for k, v in user_input.items() if v not in (None, "", [])})
            return await self.async_step_covers_menu()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Optional(CONF_CO2_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="carbon_dioxide")
                ),
                vol.Optional(CONF_HUMIDITY_INDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
                ),
                vol.Optional(CONF_HUMIDITY_OUTDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
                ),
                vol.Optional(CONF_TEMP_OUTDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Optional(CONF_TEMP_SENSORS): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature", multiple=True
                    )
                ),
                vol.Optional(CONF_FAN_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["fan", "number"])
                ),
                vol.Optional(
                    CONF_WINDOW_TEMP_MIN, default=DEFAULT_WINDOW_TEMP_MIN
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-10, max=30, step=1, unit_of_measurement="°C", mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_TEMP_MAX, default=DEFAULT_WINDOW_TEMP_MAX
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15, max=40, step=1, unit_of_measurement="°C", mode="slider"
                    )
                ),
            }),
        )

    # ------------------------------------------------------------------
    # Stap 4: covers menu
    # ------------------------------------------------------------------

    async def async_step_covers_menu(self, user_input=None):
        count = len(self._data.get(CONF_COVER_CONFIGS) or [])
        return self.async_show_menu(
            step_id="covers_menu",
            menu_options=["add_cover", "covers_done"],
            description_placeholders={"count": str(count)},
        )

    async def async_step_add_cover(self, user_input=None):
        if user_input is not None:
            configs = self._data.setdefault(CONF_COVER_CONFIGS, [])
            configs.append({k: v for k, v in user_input.items() if v not in (None, "", [])})
            return await self.async_step_covers_menu()

        return self.async_show_form(
            step_id="add_cover",
            data_schema=_cover_schema(),
        )

    async def async_step_covers_done(self, user_input=None):
        return self.async_create_entry(
            title=self._data[CONF_ZONE_NAME], data=self._data
        )


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------

class OptimalClimateOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self._entry = config_entry
        self._options: dict = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, user_input=None):
        return await self.async_step_options_menu()

    async def async_step_options_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="options_menu",
            menu_options=["add_climate", "edit_thresholds", "edit_sensors", "add_cover", "options_done"],
        )

    async def async_step_add_climate(self, user_input=None):
        if user_input is not None:
            configs = self._options.setdefault(CONF_CLIMATE_CONFIGS, [])
            configs.append({k: v for k, v in user_input.items() if v not in (None, "")})
            return await self.async_step_options_menu()

        return self.async_show_form(
            step_id="add_climate",
            data_schema=_climate_schema(),
        )

    async def async_step_edit_thresholds(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_options_menu()

        return self.async_show_form(
            step_id="edit_thresholds",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_WINDOW_TEMP_MIN,
                    default=self._options.get(CONF_WINDOW_TEMP_MIN, DEFAULT_WINDOW_TEMP_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-10, max=30, step=1, unit_of_measurement="°C", mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_TEMP_MAX,
                    default=self._options.get(CONF_WINDOW_TEMP_MAX, DEFAULT_WINDOW_TEMP_MAX),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15, max=40, step=1, unit_of_measurement="°C", mode="slider"
                    )
                ),
            }),
        )

    async def async_step_edit_sensors(self, user_input=None):
        if user_input is not None:
            self._options.update({k: v for k, v in user_input.items() if v is not None})
            return await self.async_step_options_menu()

        return self.async_show_form(
            step_id="edit_sensors",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_CO2_SENSOR,
                    default=self._options.get(CONF_CO2_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="carbon_dioxide")
                ),
                vol.Optional(
                    CONF_TEMP_SENSORS,
                    default=self._options.get(CONF_TEMP_SENSORS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature", multiple=True
                    )
                ),
                vol.Optional(
                    CONF_FAN_ENTITY,
                    default=self._options.get(CONF_FAN_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["fan", "number"])
                ),
            }),
        )

    async def async_step_add_cover(self, user_input=None):
        if user_input is not None:
            configs = self._options.setdefault(CONF_COVER_CONFIGS, [])
            configs.append({k: v for k, v in user_input.items() if v not in (None, "", [])})
            return await self.async_step_options_menu()

        return self.async_show_form(
            step_id="add_cover",
            data_schema=_cover_schema(),
        )

    async def async_step_options_done(self, user_input=None):
        return self.async_create_entry(data=self._options)


# ---------------------------------------------------------------------------
# Gedeelde form schemas
# ---------------------------------------------------------------------------

def _climate_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CC_CLIMATE_ENTITY, default=d.get(CC_CLIMATE_ENTITY, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        ),
        vol.Required(CC_CLIMATE_TYPE, default=d.get(CC_CLIMATE_TYPE, CLIMATE_TYPE_HEATING)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": CLIMATE_TYPE_HEATING,  "label": "Thermostaat (verwarming)"},
                    {"value": CLIMATE_TYPE_COOLING,  "label": "Airco (koeling)"},
                    {"value": CLIMATE_TYPE_HEAT_COOL,"label": "Warmtepomp (verwarming + koeling)"},
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(CC_CLIMATE_NAME, default=d.get(CC_CLIMATE_NAME, "")): str,
    })


def _cover_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CC_ENTITY_ID, default=d.get(CC_ENTITY_ID, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="cover")
        ),
        vol.Optional(CC_NAME, default=d.get(CC_NAME, "")): str,
        vol.Required(CC_TYPE, default=d.get(CC_TYPE, COVER_TYPE_SHUTTER)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": COVER_TYPE_SHUTTER, "label": "Shutter / rolluik"},
                    {"value": COVER_TYPE_CURTAIN, "label": "Gordijn"},
                    {"value": COVER_TYPE_WINDOW,  "label": "Automatisch raam"},
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Required(CC_AZIMUTH, default=d.get(CC_AZIMUTH, 180)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=359, step=1, unit_of_measurement="°", mode="box")
        ),
        vol.Optional(CC_FOV, default=d.get(CC_FOV, DEFAULT_FOV)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=180, step=5, unit_of_measurement="°", mode="slider")
        ),
        vol.Optional(CC_MIN_POSITION, default=d.get(CC_MIN_POSITION, DEFAULT_MIN_POSITION_SHUTTER)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=90, step=5, unit_of_measurement="%", mode="slider")
        ),
        vol.Optional(CC_SUN_PROTECTION, default=d.get(CC_SUN_PROTECTION, True)): selector.BooleanSelector(),
        vol.Optional(CC_ILLUMINANCE_SENSOR, default=d.get(CC_ILLUMINANCE_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="illuminance")
        ),
        vol.Optional(
            CC_ILLUMINANCE_THRESHOLD, default=d.get(CC_ILLUMINANCE_THRESHOLD, DEFAULT_ILLUMINANCE_THRESHOLD)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=500, max=100000, step=500, unit_of_measurement="lx", mode="box")
        ),
        vol.Optional(CC_TEMP_SENSOR, default=d.get(CC_TEMP_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Optional(CC_LINKED_CURTAIN, default=d.get(CC_LINKED_CURTAIN)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="cover")
        ),
        vol.Optional(
            CC_CURTAIN_MIN_OPEN, default=d.get(CC_CURTAIN_MIN_OPEN, DEFAULT_MIN_POSITION_CURTAIN)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=50, step=5, unit_of_measurement="%", mode="slider")
        ),
    })
