# Optimal Climate

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant custom integration that coordinates an optimal indoor climate by combining shutters, curtains, automated windows, exhaust fan, CO₂, humidity, and temperature sensors into one smart system.

## Features

- **Per-cover control** — each shutter or curtain has its own azimuth, field of view, minimum position, and illuminance sensor
- **Automatic windows** — opens windows for ventilation when CO₂ is high, outdoor temperature is within range, and paired curtain is not blocking
- **Exhaust fan control** — scales fan speed based on CO₂ level and summer cooling (outdoor cooler than indoor)
- **Comfort score** — weighted 0–100 score based on CO₂, humidity, and temperature
- **Modes** — auto / manual / away / sleep

## Installation via HACS

1. In Home Assistant: **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/Kaspermaat/Ultimate-Climate` — Category: **Integration**
3. Download and restart Home Assistant
4. **Settings → Integrations → Add → Optimal Climate**

## Configuration

The setup wizard walks you through 3 steps:

1. **Zone** — name + optional climate entity (thermostat / AC)
2. **Sensors** — CO₂, humidity (indoor/outdoor), outdoor temperature, extra indoor temperature sensors, exhaust fan entity
3. **Covers** — add shutters, curtains and automated windows one by one, each with their own settings

### Per-cover settings

| Setting | Description |
|---|---|
| Type | Shutter / Curtain / Automated window |
| Azimuth | Compass direction the cover faces (180 = south) |
| Field of view | How wide the window "sees" sun (default ±90°) |
| Min position | Minimum open % during sun protection (e.g. 15 = never more than 85% closed) |
| Illuminance sensor | Optional lux sensor for this specific cover |
| Illuminance threshold | Lux level above which sun protection activates |
| Temperature sensor | Optional per-cover temperature sensor |
| Linked curtain | Curtain that must be open before this window opens |

## Entities created per zone

| Entity | Description |
|---|---|
| `sensor.{zone}_comfortscore` | Comfort score 0–100% |
| `sensor.{zone}_co2_status` | goed / matig / slecht / kritiek |
| `sensor.{zone}_ventilatie_advies` | Ventilation advice + attributes |
| `sensor.{zone}_vochtbalans` | Indoor vs outdoor humidity delta |
| `sensor.{zone}_co2_trend` | stijgend / dalend / stabiel |
| `sensor.{zone}_afzuiging_advies` | Fan speed advice in % |
| `sensor.{zone}_covers_overzicht` | Average cover position + per-cover details |
| `select.{zone}_modus` | Mode selector (auto / manual / away / sleep) |

## Service

```yaml
service: optimal_climate.recalculate
data:
  config_entry_id: ""  # optional — empty = all zones
```
