# Inforcer

Home Assistant integration for [Inforcer](https://www.inforcer.com), a Microsoft 365 tenant management and security alignment platform for MSPs.

Reads from the Inforcer Beta REST API (read-only) and exposes:

- Tenants onboarded (count)
- Alignment score overall, plus one sensor per baseline
- Secure score overall, plus one sensor per tenant

## Requirements

- An Inforcer account with API access (Admin privileges in Inforcer)
- An API key generated from the Inforcer UI

## Setup

1. Install via HACS (custom repository) and restart Home Assistant.
2. Settings > Devices & Services > Add Integration > **Inforcer**.
3. Pick your region (ANZ / EU / UK / US).
4. Paste your API key.

⚠️ The Inforcer REST API is currently in **Beta**. Endpoints and response shapes may change without notice.
