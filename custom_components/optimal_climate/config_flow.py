"""Config flow: four-step wizard (zone → sensors → covers → gordijnen)."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_CO2_SENSOR,
    CONF_COVER_ENTITIES,
    CONF_CURTAIN_MIN_OPEN,
    CONF_FAN_ENTITY,
    CONF_HUMIDITY_INDOOR,
    CONF_HUMIDITY_OUTDOOR,
    CONF_TEMP_OUTDOOR,
    CONF_WINDOW_AZIMUTH,
    CONF_WINDOW_CURTAIN_MAP,
    CONF_WINDOW_ENTITIES,
    CONF_WINDOW_FOV,
    CONF_WINDOW_TEMP_MAX,
    CONF_WINDOW_TEMP_MIN,
    CONF_ZONE_NAME,
    DEFAULT_CURTAIN_MIN_OPEN,
    DEFAULT_WINDOW_AZIMUTH,
    DEFAULT_WINDOW_FOV,
    DEFAULT_WINDOW_TEMP_MAX,
    DEFAULT_WINDOW_TEMP_MIN,
    DOMAIN,
)


class OptimalClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptimalClimateOptionsFlow:
        return OptimalClimateOptionsFlow(config_entry)

    # ------------------------------------------------------------------
    # Stap 1: zone naam + climate entity
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_ZONE_NAME, default="Woonkamer"): str,
                vol.Optional(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"step": "1 / 4"},
        )

    # ------------------------------------------------------------------
    # Stap 2: sensoren + afzuiging + temperatuurbereik ramen
    # ------------------------------------------------------------------

    async def async_step_sensors(self, user_input=None):
        if user_input is not None:
            self._data.update({k: v for k, v in user_input.items() if v is not None})
            return await self.async_step_covers()

        schema = vol.Schema(
            {
                vol.Optional(CONF_CO2_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="carbon_dioxide"
                    )
                ),
                vol.Optional(CONF_HUMIDITY_INDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="humidity"
                    )
                ),
                vol.Optional(CONF_HUMIDITY_OUTDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="humidity"
                    )
                ),
                vol.Optional(CONF_TEMP_OUTDOOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature"
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
            }
        )
        return self.async_show_form(
            step_id="sensors",
            data_schema=schema,
            description_placeholders={"step": "2 / 4"},
        )

    # ------------------------------------------------------------------
    # Stap 3: covers en ramen
    # ------------------------------------------------------------------

    async def async_step_covers(self, user_input=None):
        if user_input is not None:
            self._data.update({k: v for k, v in user_input.items() if v is not None})
            return await self.async_step_curtains()

        schema = vol.Schema(
            {
                vol.Optional(CONF_COVER_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="cover", multiple=True)
                ),
                vol.Optional(CONF_WINDOW_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="cover", multiple=True)
                ),
                vol.Optional(
                    CONF_WINDOW_AZIMUTH, default=DEFAULT_WINDOW_AZIMUTH
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=359, step=1, unit_of_measurement="°", mode="box"
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_FOV, default=DEFAULT_WINDOW_FOV
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=180, step=5, unit_of_measurement="°", mode="slider"
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="covers",
            data_schema=schema,
            description_placeholders={"step": "3 / 4"},
        )

    # ------------------------------------------------------------------
    # Stap 4: gordijn-raam koppelingen (dynamisch per raam)
    # ------------------------------------------------------------------

    async def async_step_curtains(self, user_input=None):
        windows: list[str] = list(self._data.get(CONF_WINDOW_ENTITIES) or [])

        if not windows:
            # Geen ramen geconfigureerd — stap overslaan
            return self.async_create_entry(
                title=self._data[CONF_ZONE_NAME], data=self._data
            )

        if user_input is not None:
            curtain_map: dict[str, str] = {}
            for window_id in windows:
                key = _curtain_key(window_id)
                curtain = user_input.get(key)
                if curtain:
                    curtain_map[window_id] = curtain

            min_open = user_input.get(CONF_CURTAIN_MIN_OPEN, DEFAULT_CURTAIN_MIN_OPEN)

            self._data[CONF_WINDOW_CURTAIN_MAP] = curtain_map
            self._data[CONF_CURTAIN_MIN_OPEN] = min_open

            return self.async_create_entry(
                title=self._data[CONF_ZONE_NAME], data=self._data
            )

        # Bouw een dynamisch formulier: één gordijn-selector per raam
        schema_fields: dict = {}
        for window_id in windows:
            schema_fields[vol.Optional(_curtain_key(window_id))] = (
                selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="cover")
                )
            )

        schema_fields[
            vol.Optional(CONF_CURTAIN_MIN_OPEN, default=DEFAULT_CURTAIN_MIN_OPEN)
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=50, step=5, unit_of_measurement="%", mode="slider"
            )
        )

        return self.async_show_form(
            step_id="curtains",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "step": "4 / 4",
                "window_count": str(len(windows)),
            },
        )


def _curtain_key(window_entity_id: str) -> str:
    """Stable form field key for a window entity."""
    return f"curtain__{window_entity_id.replace('.', '__')}"


# ---------------------------------------------------------------------------
# Options flow — aanpasbaar na initiële setup
# ---------------------------------------------------------------------------

class OptimalClimateOptionsFlow(config_entries.OptionsFlow):
    """Laat gebruikers drempelwaarden aanpassen zonder opnieuw te installeren."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        # Merge bestaande data + opties als startpunt
        self._options: dict = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, user_input=None):
        return await self.async_step_thresholds()

    # ------------------------------------------------------------------
    # Stap 1: drempelwaarden (meest aangepast na setup)
    # ------------------------------------------------------------------

    async def async_step_thresholds(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_options_sensors()

        schema = vol.Schema(
            {
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
                vol.Optional(
                    CONF_CURTAIN_MIN_OPEN,
                    default=self._options.get(CONF_CURTAIN_MIN_OPEN, DEFAULT_CURTAIN_MIN_OPEN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=50, step=5, unit_of_measurement="%", mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_AZIMUTH,
                    default=self._options.get(CONF_WINDOW_AZIMUTH, DEFAULT_WINDOW_AZIMUTH),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=359, step=1, unit_of_measurement="°", mode="box"
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_FOV,
                    default=self._options.get(CONF_WINDOW_FOV, DEFAULT_WINDOW_FOV),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=180, step=5, unit_of_measurement="°", mode="slider"
                    )
                ),
            }
        )
        return self.async_show_form(step_id="thresholds", data_schema=schema)

    # ------------------------------------------------------------------
    # Stap 2: sensoren / afzuiging wisselen
    # ------------------------------------------------------------------

    async def async_step_options_sensors(self, user_input=None):
        if user_input is not None:
            self._options.update({k: v for k, v in user_input.items() if v is not None})
            return self.async_create_entry(data=self._options)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CO2_SENSOR,
                    default=self._options.get(CONF_CO2_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="carbon_dioxide"
                    )
                ),
                vol.Optional(
                    CONF_HUMIDITY_INDOOR,
                    default=self._options.get(CONF_HUMIDITY_INDOOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="humidity"
                    )
                ),
                vol.Optional(
                    CONF_HUMIDITY_OUTDOOR,
                    default=self._options.get(CONF_HUMIDITY_OUTDOOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="humidity"
                    )
                ),
                vol.Optional(
                    CONF_TEMP_OUTDOOR,
                    default=self._options.get(CONF_TEMP_OUTDOOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature"
                    )
                ),
                vol.Optional(
                    CONF_FAN_ENTITY,
                    default=self._options.get(CONF_FAN_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["fan", "number"])
                ),
            }
        )
        return self.async_show_form(step_id="options_sensors", data_schema=schema)
