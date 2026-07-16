"""Thin async client for the Inforcer Beta REST API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import API_KEY_HEADER, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class InforcerApiError(Exception):
    """Generic error talking to the Inforcer API."""


class InforcerAuthError(InforcerApiError):
    """Raised on HTTP 401 - the API key is invalid, expired, or revoked."""


class InforcerRateLimitError(InforcerApiError):
    """Raised on HTTP 429 - the per-key rate limit was exceeded."""


class InforcerConnectionError(InforcerApiError):
    """Raised on network/timeout failures reaching the Inforcer API."""


class InforcerClient:
    """Small wrapper around the Inforcer Beta REST API.

    The API is Beta and read-only. Every response is expected to use the
    envelope documented by Inforcer: `{"data": ..., "status": "success"}` on
    success or `{"error": ..., "status": "error", "code": ...}` on failure.
    """

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, api_key: str
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Call an endpoint and return the `data` payload.

        Never logs the API key. Raises a specific `InforcerApiError` subclass
        so callers (the coordinator) can react distinctly to auth failures,
        rate limiting, and connectivity issues.
        """
        url = f"{self._base_url}{path}"
        headers = {API_KEY_HEADER: self._api_key}

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, headers=headers, json=json, params=params
                ) as resp:
                    if resp.status == 401:
                        raise InforcerAuthError("Inforcer API key is invalid or expired")
                    if resp.status == 429:
                        raise InforcerRateLimitError(
                            "Inforcer API rate limit exceeded"
                        )

                    try:
                        payload = await resp.json()
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        resp.raise_for_status()
                        raise InforcerApiError(
                            f"Unexpected response from Inforcer API ({resp.status})"
                        ) from err

                    if resp.status >= 500:
                        raise InforcerApiError(
                            f"Inforcer API server error ({resp.status})"
                        )

                    if payload.get("status") == "error" or resp.status >= 400:
                        raise InforcerApiError(
                            payload.get("error", f"Inforcer API error ({resp.status})")
                        )

                    return payload.get("data")
        except TimeoutError as err:
            raise InforcerConnectionError(
                "Timed out contacting the Inforcer API"
            ) from err
        except aiohttp.ClientError as err:
            raise InforcerConnectionError(
                f"Error contacting the Inforcer API: {err}"
            ) from err

    async def async_get_tenants(self) -> list[dict[str, Any]]:
        """Return all onboarded tenants."""
        data = await self._request("GET", "/beta/tenants")
        return data or []

    async def async_get_alignment_scores(self) -> list[dict[str, Any]]:
        """Return alignment results and metrics."""
        data = await self._request("GET", "/beta/alignmentScores")
        return data or []

    async def async_get_baselines(self) -> list[dict[str, Any]]:
        """Return baseline info and tenant assignment."""
        data = await self._request("GET", "/beta/baselines")
        return data or []

    async def async_get_tenant_secure_scores(self, tenant_id: str) -> Any:
        """Return secure score data for a single tenant.

        The exact schema for this endpoint isn't documented publicly (single
        current score vs. a history list). Callers should treat the return
        value defensively - see `coordinator.py` for the parsing logic.
        """
        return await self._request(
            "GET", f"/beta/tenants/{tenant_id}/secureScores"
        )
