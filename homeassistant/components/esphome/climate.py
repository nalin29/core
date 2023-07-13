"""Support for ESPHome climate devices."""
from __future__ import annotations

from typing import Any, cast

from aioesphomeapi import (
    ClimateAction,
    ClimateFanMode,
    ClimateInfo,
    ClimateMode,
    ClimatePreset,
    ClimateState,
    ClimateSwingMode,
    EntityInfo,
)

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_FOCUS,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_MIDDLE,
    FAN_OFF,
    FAN_ON,
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_VERTICAL,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    EsphomeEntity,
    esphome_state_property,
    platform_async_setup_entry,
)
from .enum_mapper import EsphomeEnumMapper

FAN_QUIET = "quiet"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ESPHome climate devices based on a config entry."""
    await platform_async_setup_entry(
        hass,
        entry,
        async_add_entities,
        info_type=ClimateInfo,
        entity_type=EsphomeClimateEntity,
        state_type=ClimateState,
    )


_CLIMATE_MODES: EsphomeEnumMapper[ClimateMode, HVACMode] = EsphomeEnumMapper(
    {
        ClimateMode.OFF: HVACMode.OFF,
        ClimateMode.HEAT_COOL: HVACMode.HEAT_COOL,
        ClimateMode.COOL: HVACMode.COOL,
        ClimateMode.HEAT: HVACMode.HEAT,
        ClimateMode.FAN_ONLY: HVACMode.FAN_ONLY,
        ClimateMode.DRY: HVACMode.DRY,
        ClimateMode.AUTO: HVACMode.AUTO,
    }
)
_CLIMATE_ACTIONS: EsphomeEnumMapper[ClimateAction, HVACAction] = EsphomeEnumMapper(
    {
        ClimateAction.OFF: HVACAction.OFF,
        ClimateAction.COOLING: HVACAction.COOLING,
        ClimateAction.HEATING: HVACAction.HEATING,
        ClimateAction.IDLE: HVACAction.IDLE,
        ClimateAction.DRYING: HVACAction.DRYING,
        ClimateAction.FAN: HVACAction.FAN,
    }
)
_FAN_MODES: EsphomeEnumMapper[ClimateFanMode, str] = EsphomeEnumMapper(
    {
        ClimateFanMode.ON: FAN_ON,
        ClimateFanMode.OFF: FAN_OFF,
        ClimateFanMode.AUTO: FAN_AUTO,
        ClimateFanMode.LOW: FAN_LOW,
        ClimateFanMode.MEDIUM: FAN_MEDIUM,
        ClimateFanMode.HIGH: FAN_HIGH,
        ClimateFanMode.MIDDLE: FAN_MIDDLE,
        ClimateFanMode.FOCUS: FAN_FOCUS,
        ClimateFanMode.DIFFUSE: FAN_DIFFUSE,
        ClimateFanMode.QUIET: FAN_QUIET,
    }
)
_SWING_MODES: EsphomeEnumMapper[ClimateSwingMode, str] = EsphomeEnumMapper(
    {
        ClimateSwingMode.OFF: SWING_OFF,
        ClimateSwingMode.BOTH: SWING_BOTH,
        ClimateSwingMode.VERTICAL: SWING_VERTICAL,
        ClimateSwingMode.HORIZONTAL: SWING_HORIZONTAL,
    }
)
_PRESETS: EsphomeEnumMapper[ClimatePreset, str] = EsphomeEnumMapper(
    {
        ClimatePreset.NONE: PRESET_NONE,
        ClimatePreset.HOME: PRESET_HOME,
        ClimatePreset.AWAY: PRESET_AWAY,
        ClimatePreset.BOOST: PRESET_BOOST,
        ClimatePreset.COMFORT: PRESET_COMFORT,
        ClimatePreset.ECO: PRESET_ECO,
        ClimatePreset.SLEEP: PRESET_SLEEP,
        ClimatePreset.ACTIVITY: PRESET_ACTIVITY,
    }
)


class EsphomeClimateEntity(EsphomeEntity[ClimateInfo, ClimateState], ClimateEntity):
    """A climate implementation for ESPHome."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @callback
    def _on_static_info_update(self, static_info: EntityInfo) -> None:
        """Set attrs from static info."""
        super()._on_static_info_update(static_info)
        static_info = self._static_info
        self._attr_precision = self._get_precision()
        self._attr_hvac_modes = [
            _CLIMATE_MODES.from_esphome(mode) for mode in static_info.supported_modes
        ]
        self._attr_fan_modes = [
            _FAN_MODES.from_esphome(mode) for mode in static_info.supported_fan_modes
        ] + static_info.supported_custom_fan_modes
        self._attr_preset_modes = [
            _PRESETS.from_esphome(preset)
            for preset in static_info.supported_presets_compat(self._api_version)
        ] + static_info.supported_custom_presets
        self._attr_swing_modes = [
            _SWING_MODES.from_esphome(mode)
            for mode in static_info.supported_swing_modes
        ]
        # Round to one digit because of floating point math
        self._attr_target_temperature_step = round(
            static_info.visual_target_temperature_step, 1
        )
        self._attr_min_temp = static_info.visual_min_temperature
        self._attr_max_temp = static_info.visual_max_temperature
        features = ClimateEntityFeature(0)
        if self._static_info.supports_two_point_target_temperature:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self.preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        if self.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self.swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = features

    def _get_precision(self) -> float:
        """Return the precision of the climate device."""
        precicions = [PRECISION_WHOLE, PRECISION_HALVES, PRECISION_TENTHS]
        static_info = self._static_info
        if static_info.visual_current_temperature_step != 0:
            step = static_info.visual_current_temperature_step
        else:
            step = static_info.visual_target_temperature_step
        for prec in precicions:
            if step >= prec:
                return prec
        # Fall back to highest precision, tenths
        return PRECISION_TENTHS

    @property
    @esphome_state_property
    def hvac_mode(self) -> HVACMode | None:
        """Return current operation ie. heat, cool, idle."""
        return _CLIMATE_MODES.from_esphome(self._state.mode)

    @property
    @esphome_state_property
    def hvac_action(self) -> HVACAction | None:
        """Return current action."""
        # HA has no support feature field for hvac_action
        if not self._static_info.supports_action:
            return None
        return _CLIMATE_ACTIONS.from_esphome(self._state.action)

    @property
    @esphome_state_property
    def fan_mode(self) -> str | None:
        """Return current fan setting."""
        state = self._state
        return state.custom_fan_mode or _FAN_MODES.from_esphome(state.fan_mode)

    @property
    @esphome_state_property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        state = self._state
        return state.custom_preset or _PRESETS.from_esphome(
            state.preset_compat(self._api_version)
        )

    @property
    @esphome_state_property
    def swing_mode(self) -> str | None:
        """Return current swing mode."""
        return _SWING_MODES.from_esphome(self._state.swing_mode)

    @property
    @esphome_state_property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._state.current_temperature

    @property
    @esphome_state_property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._state.target_temperature

    @property
    @esphome_state_property
    def target_temperature_low(self) -> float | None:
        """Return the lowbound target temperature we try to reach."""
        return self._state.target_temperature_low

    @property
    @esphome_state_property
    def target_temperature_high(self) -> float | None:
        """Return the highbound target temperature we try to reach."""
        return self._state.target_temperature_high

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (and operation mode if set)."""
        data: dict[str, Any] = {"key": self._key}
        if ATTR_HVAC_MODE in kwargs:
            data["mode"] = _CLIMATE_MODES.from_hass(
                cast(HVACMode, kwargs[ATTR_HVAC_MODE])
            )
        if ATTR_TEMPERATURE in kwargs:
            data["target_temperature"] = kwargs[ATTR_TEMPERATURE]
        if ATTR_TARGET_TEMP_LOW in kwargs:
            data["target_temperature_low"] = kwargs[ATTR_TARGET_TEMP_LOW]
        if ATTR_TARGET_TEMP_HIGH in kwargs:
            data["target_temperature_high"] = kwargs[ATTR_TARGET_TEMP_HIGH]
        await self._client.climate_command(**data)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target operation mode."""
        await self._client.climate_command(
            key=self._key, mode=_CLIMATE_MODES.from_hass(hvac_mode)
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        kwargs: dict[str, Any] = {"key": self._key}
        if preset_mode in self._static_info.supported_custom_presets:
            kwargs["custom_preset"] = preset_mode
        else:
            kwargs["preset"] = _PRESETS.from_hass(preset_mode)
        await self._client.climate_command(**kwargs)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        kwargs: dict[str, Any] = {"key": self._key}
        if fan_mode in self._static_info.supported_custom_fan_modes:
            kwargs["custom_fan_mode"] = fan_mode
        else:
            kwargs["fan_mode"] = _FAN_MODES.from_hass(fan_mode)
        await self._client.climate_command(**kwargs)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode."""
        await self._client.climate_command(
            key=self._key, swing_mode=_SWING_MODES.from_hass(swing_mode)
        )
