"""The Inforcer integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InforcerClient
from .const import (
    CONF_API_KEY,
    CONF_REGION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    REGIONS,
)
from .coordinator import InforcerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

InforcerConfigEntry: TypeAlias = ConfigEntry[InforcerDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: InforcerConfigEntry) -> bool:
    """Set up Inforcer from a config entry."""
    session = async_get_clientsession(hass)
    client = InforcerClient(
        session, REGIONS[entry.data[CONF_REGION]], entry.data[CONF_API_KEY]
    )

    update_minutes = entry.options.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES
    )
    coordinator = InforcerDataUpdateCoordinator(
        hass, entry, client, timedelta(minutes=update_minutes)
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InforcerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: InforcerConfigEntry) -> None:
    """Reload the entry when options (poll interval / rotated key) change."""
    await hass.config_entries.async_reload(entry.entry_id)
