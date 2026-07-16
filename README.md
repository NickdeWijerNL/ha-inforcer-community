# Inforcer for Home Assistant

A custom Home Assistant integration for [Inforcer](https://www.inforcer.com), a Microsoft 365 tenant management and security alignment platform for MSPs. It reads from Inforcer's Beta REST API (read-only) and exposes tenant, alignment, and secure score data as sensors.

> ⚠️ **Beta API notice.** The Inforcer REST API is currently in Beta. Endpoints, authentication, and response shapes may change without notice from Inforcer. Some parsing in this integration (notably the per-tenant secure score endpoint, whose schema isn't publicly documented) is written defensively against the documented response envelope and may need adjustment once you can confirm the exact shape your account receives — see [Known limitations](#known-limitations).

## Prerequisites

- An Inforcer account with API access enabled. Generating API keys requires **Admin** privileges within Inforcer.
- Home Assistant 2024.8 or newer.
- [HACS](https://hacs.xyz) installed, if adding this as a custom repository (recommended).

## Generating an API key

1. Sign in to the Inforcer UI.
2. Go to **Configure > REST API**.
3. Create a new key. **Copy it immediately** — Inforcer only shows the key once, at creation time.
4. Note the expiry date your organization's policy applies to the key

## Installation

### Via HACS (custom repository)

1. In HACS, go to **Integrations > ⋮ > Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Install **Inforcer**, then restart Home Assistant.

### Manual

Copy `custom_components/inforcer` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. **Settings > Devices & Services > Add Integration**, search for **Inforcer**.
2. **Step 1:** choose your region — ANZ, EU, UK, or US. This determines the API base URL used for every request.
3. **Step 2:** paste your API key. It's validated immediately against `GET /beta/tenants` before the entry is created; you'll get a specific error if the key is invalid/expired (401), you're rate limited (429), or the API can't be reached.

Only one Inforcer config entry is supported per region (matching one Inforcer account/device per region).

## Rotating your API key

Inforcer keys expire and can't be retrieved once created, so this integration supports two ways to update the stored key without deleting and re-adding the integration:

- **Automatic reauth:** if a request ever returns 401 (key expired or revoked), Home Assistant will surface a "reauthentication required" notification for this integration. Follow it to enter a new key.
- **Proactive rotation:** open the integration's **Configure** (options flow) at any time and enter a new key before the old one expires. Leave the field blank to keep the current key and only change the poll interval.

The options flow is also where you adjust the **update interval** (default 20 minutes, configurable between 15 minutes and 2 hours).

## Entity structure

One Home Assistant **device** represents the Inforcer account/region as a whole (e.g. "Inforcer (EU)"), holding:

- **Tenants onboarded** — total tenant count from `/beta/tenants`.
- **Alignment score overall** — averaged across baselines.
- **Alignment score – `<baseline name>`** — one sensor per baseline returned by `/beta/baselines`, joined against `/beta/alignmentScores`.
- **Secure score overall** — averaged across all tenants' secure scores, with each tenant's individual score also available as an attribute on this sensor for quick reference.

In addition, each tenant gets its **own device** (linked to the account device via `via_device`) with a **Secure score** sensor. This was chosen over lumping all tenants into the account device because:

- For a single-tenant admin, this is just one extra device with one sensor — negligible overhead.
- For an MSP managing many tenants, per-tenant devices let you use Home Assistant's device/area grouping, dashboards, and automations (e.g. "notify me if any tenant's secure score drops below X") per client, rather than parsing a single overloaded attribute blob.

Baseline and tenant sensors are added dynamically as they appear in Inforcer — no restart needed when a new tenant or baseline shows up; entities become available on the next successful poll.

## Rate limits and polling

Inforcer allows 400 requests/minute per API key, with server-side response caching for 300 seconds per key/endpoint pair. Each poll makes exactly 3 requests — `/beta/tenants`, `/beta/alignmentScores`, `/beta/baselines` — regardless of tenant count: `/beta/tenants` already includes each tenant's current secure score inline, so no per-tenant fan-out is needed. The default 20-minute poll interval stays comfortably under the limit even for large MSP tenant counts.

## Error handling

- **401** — triggers Home Assistant's reauth flow; entities remain at their last known state until reauthenticated.
- **429** — the current poll is skipped and retried on the next interval; sensors become `unavailable` if this persists.
- **5xx / timeouts / connection errors** — logged and surfaced as `unavailable` entities rather than crashing the integration.

Logs use `custom_components.inforcer` as the logger name and never include the API key.

## Known limitations

- Secure score is read directly from the `secureScore` field on each `/beta/tenants` entry (confirmed against a live account). The dedicated `/beta/tenants/{tenantId}/secureScores` endpoint mentioned in Inforcer's beta docs is not called by this integration — it wasn't needed once the inline field was confirmed, and skipping it keeps polling to a fixed 3 requests regardless of tenant count. If that endpoint turns out to expose richer history/control-level detail you want surfaced, please open an issue.
- Baseline join key (`baselineGroupId` on alignment score entries, matched against a baseline's `id`), tenant identifier (`clientTenantId`) and tenant name (`tenantFriendlyName`) were all confirmed against a live account's responses — see the candidate-key comment at the top of `coordinator.py` if Inforcer changes these field names in a future beta revision.
- A baseline with no tenant currently evaluated against it (e.g. an unused blueprint template) will correctly show its alignment sensor as `unknown` — there is no score to report, not a parsing bug.

## Development

```
custom_components/inforcer/
├── __init__.py         # entry setup/unload, coordinator wiring
├── api.py               # thin async REST client, typed error hierarchy
├── config_flow.py        # region + API key setup, reauth, options flow
├── const.py              # domain, regions, defaults
├── coordinator.py        # DataUpdateCoordinator, response parsing/aggregation
├── sensor.py              # sensor entities, dynamic per-baseline/per-tenant creation
├── manifest.json
├── strings.json
└── translations/
    ├── en.json
    └── nl.json
```
