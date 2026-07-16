"""DataUpdateCoordinator for the Inforcer integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    InforcerApiError,
    InforcerAuthError,
    InforcerClient,
    InforcerConnectionError,
    InforcerRateLimitError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Candidate key names tried in order when parsing beta-endpoint payloads.
# Confirmed against a live account: tenants use clientTenantId/tenantFriendlyName,
# baselines use id/name, and alignment score entries reference their baseline via
# baselineGroupId (joined against a baseline's id).
_ID_KEYS = ("id", "clientTenantId", "tenantId", "baselineId", "_id")
_NAME_KEYS = ("name", "tenantFriendlyName", "tenantName", "baselineName", "displayName")
_BASELINE_REF_KEYS = ("baselineGroupId", "baselineId", "baseline_id")
_SCORE_KEYS = ("score", "alignmentScore", "secureScore", "currentScore", "value", "percentage")
_HISTORY_KEYS = ("history", "scores", "results")
_DATE_KEYS = ("date", "recordedDateTime", "createdAt", "timestamp")


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


def _extract_score(value: Any) -> float | None:
    """Best-effort extraction of a numeric score from a beta-endpoint value.

    Handles a bare number, a dict with a score-like key, a dict/list wrapping
    a history of scores (takes the most recent), or nested combinations of
    the above. Returns None rather than raising if nothing recognizable is
    found - callers surface that as an unavailable sensor, not a crash.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        score = _first(value, _SCORE_KEYS)
        if isinstance(score, (int, float)):
            return float(score)
        history = _first(value, _HISTORY_KEYS)
        if history is not None:
            return _extract_score(history)
        return None
    if isinstance(value, list) and value:
        # Assume chronological order; prefer an explicit date field if present.
        def sort_key(item: Any) -> Any:
            if isinstance(item, dict):
                return _first(item, _DATE_KEYS) or ""
            return ""

        try:
            latest = sorted(value, key=sort_key)[-1]
        except TypeError:
            latest = value[-1]
        return _extract_score(latest)
    return None


@dataclass
class BaselineScore:
    """Alignment score for a single baseline."""

    baseline_id: str
    name: str
    score: float | None


@dataclass
class TenantSecureScore:
    """Secure score for a single tenant, sourced from /beta/tenants directly."""

    tenant_id: str
    name: str
    score: float | None


@dataclass
class InforcerData:
    """Aggregated data produced by one coordinator refresh."""

    tenants: list[dict[str, Any]] = field(default_factory=list)
    alignment_overall: float | None = None
    baseline_scores: list[BaselineScore] = field(default_factory=list)
    secure_score_overall: float | None = None
    tenant_secure_scores: list[TenantSecureScore] = field(default_factory=list)

    @property
    def tenant_count(self) -> int:
        return len(self.tenants)


class InforcerDataUpdateCoordinator(DataUpdateCoordinator[InforcerData]):
    """Coordinates all polling for a single Inforcer config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: InforcerClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        self._client = client

    async def _async_update_data(self) -> InforcerData:
        try:
            tenants = await self._client.async_get_tenants()
            alignment_scores = await self._client.async_get_alignment_scores()
            baselines = await self._client.async_get_baselines()
        except InforcerAuthError as err:
            raise ConfigEntryAuthFailed(
                "Inforcer API key was rejected (401) - a new key is required"
            ) from err
        except InforcerRateLimitError as err:
            raise UpdateFailed(
                "Inforcer API rate limit reached; will retry next interval"
            ) from err
        except InforcerConnectionError as err:
            raise UpdateFailed(f"Could not reach the Inforcer API: {err}") from err
        except InforcerApiError as err:
            raise UpdateFailed(f"Inforcer API returned an error: {err}") from err

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Raw /beta/tenants payload: %s", tenants)
            _LOGGER.debug("Raw /beta/alignmentScores payload: %s", alignment_scores)
            _LOGGER.debug("Raw /beta/baselines payload: %s", baselines)

        tenant_secure_scores = self._build_tenant_secure_scores(tenants)
        baseline_scores = self._build_baseline_scores(baselines, alignment_scores)
        alignment_overall = self._build_overall_alignment(
            alignment_scores, baseline_scores
        )

        secure_values = [
            t.score for t in tenant_secure_scores if t.score is not None
        ]
        secure_overall = (
            sum(secure_values) / len(secure_values) if secure_values else None
        )

        return InforcerData(
            tenants=tenants,
            alignment_overall=alignment_overall,
            baseline_scores=baseline_scores,
            secure_score_overall=secure_overall,
            tenant_secure_scores=tenant_secure_scores,
        )

    @staticmethod
    def _build_tenant_secure_scores(
        tenants: list[dict[str, Any]],
    ) -> list[TenantSecureScore]:
        # /beta/tenants already includes each tenant's current secureScore
        # inline, so no per-tenant /beta/tenants/{id}/secureScores fan-out is
        # needed for a current-value sensor - confirmed against a live account.
        results: list[TenantSecureScore] = []
        for tenant in tenants:
            if not isinstance(tenant, dict):
                continue
            tenant_id = str(_first(tenant, _ID_KEYS) or "")
            name = _first(tenant, _NAME_KEYS) or tenant_id or "Unknown tenant"
            results.append(
                TenantSecureScore(
                    tenant_id=tenant_id, name=name, score=_extract_score(tenant)
                )
            )
        return results

    @staticmethod
    def _build_baseline_scores(
        baselines: list[dict[str, Any]],
        alignment_scores: list[dict[str, Any]],
    ) -> list[BaselineScore]:
        # Index alignment score entries by baseline id so they can be joined
        # against the baselines list, e.g. averaging across tenants assigned
        # to the same baseline.
        scores_by_baseline: dict[str, list[float]] = {}
        for entry in alignment_scores:
            if not isinstance(entry, dict):
                continue
            baseline_id = _first(entry, _BASELINE_REF_KEYS)
            if baseline_id is None:
                continue
            score = _extract_score(entry)
            if score is not None:
                scores_by_baseline.setdefault(str(baseline_id), []).append(score)

        results: list[BaselineScore] = []
        for baseline in baselines:
            if not isinstance(baseline, dict):
                continue
            baseline_id = str(_first(baseline, _ID_KEYS) or "")
            name = _first(baseline, _NAME_KEYS) or baseline_id or "Unknown baseline"
            values = scores_by_baseline.get(baseline_id)
            score = sum(values) / len(values) if values else _extract_score(baseline)
            results.append(
                BaselineScore(baseline_id=baseline_id, name=name, score=score)
            )
        return results

    @staticmethod
    def _build_overall_alignment(
        alignment_scores: list[dict[str, Any]],
        baseline_scores: list[BaselineScore],
    ) -> float | None:
        values = [b.score for b in baseline_scores if b.score is not None]
        if values:
            return sum(values) / len(values)
        # Fall back to averaging raw alignment score entries directly if no
        # baseline join was possible.
        raw_values = [
            s
            for s in (_extract_score(e) for e in alignment_scores)
            if s is not None
        ]
        return sum(raw_values) / len(raw_values) if raw_values else None
