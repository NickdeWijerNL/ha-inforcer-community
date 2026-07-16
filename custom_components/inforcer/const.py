"""Constants for the Inforcer integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "inforcer"

CONF_REGION: Final = "region"
CONF_API_KEY: Final = "api_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"

REGIONS: Final[dict[str, str]] = {
    "anz": "https://api-anz.inforcer.com/api",
    "eu": "https://api-eu.inforcer.com/api",
    "uk": "https://api-uk.inforcer.com/api",
    "us": "https://api-us.inforcer.com/api",
}

API_KEY_HEADER: Final = "Inf-Api-Key"

DEFAULT_UPDATE_INTERVAL_MINUTES: Final = 20
MIN_UPDATE_INTERVAL_MINUTES: Final = 15
MAX_UPDATE_INTERVAL_MINUTES: Final = 120

DEFAULT_UPDATE_INTERVAL: Final = timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)

REQUEST_TIMEOUT: Final = 30

MANUFACTURER: Final = "Inforcer"
