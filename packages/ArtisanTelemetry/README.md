# ArtisanROM telemetry

Opt-in installation/activity counts and structured problem reports for the three Exynos S10 models. The native Artisan menu explains the payload, enables participation, previews manual reports and requests deletion. The default is off. Local OC learning runs independently of telemetry.

## Deployment

The production Worker origin is configured in `target/beyond1lte/oneui9/telemetry.json`. `wrangler.jsonc` binds the deployed `artisanrom-telemetry` D1 database. The administrative key and installation salt are Cloudflare secrets; neither is included in ROM images or this checkout.

## First-time Cloudflare setup

From this directory, install dependencies, authenticate and create the D1 database:

```sh
npm install
npx wrangler login
npx wrangler d1 create artisanrom-telemetry
```

Put the returned database ID into `wrangler.jsonc`. Apply the schema and set two independently generated random secrets of at least 32 characters:

```sh
npx wrangler d1 execute artisanrom-telemetry --remote --file schema.sql
npx wrangler secret put INSTALLATION_SALT
npx wrangler secret put ADMIN_TOKEN
npx wrangler deploy
```

Retain the installation salt across deployments so existing records remain deduplicated and deletable. Keep secrets in Cloudflare, never in ROM images or source. The configured binding limits ingestion to 120 requests per minute per Cloudflare location and opaque network key, without storing the address in D1. The payload is public-client, self-reported data, not proof of a unique person.

## ROM configuration

The candidate pipeline uses the maintained public origin by default and writes it with the ROM version to `/system/etc/artisan-telemetry.json`. `prepare_s10_family_candidate.py --telemetry-endpoint https://your-worker.example` overrides it for another deployment. An explicitly empty endpoint disables sharing availability.

## Statistics and retention

Open the Worker origin and enter the admin token to load totals, daily activity, model/build breakdowns and issues. The token stays in page memory; it is sent only as an HTTPS authorisation header. `/v1/stats` is protected by the same token.

Counts cover opted-in installations active within 90 days. A clean data reset can create another installation ID. Daily retries are deduplicated. Crash counts are daily signature observations, not exact crash occurrence totals. No IP, serial, IMEI, account, raw exception message or full log is stored. Cloudflare still handles network requests as the hosting provider. Scheduled cleanup retains 90 days; the menu can delete an installation sooner.

## Verification

```sh
node --test test/worker.test.mjs
```

The tests use SQLite in memory to check schema execution, retries, authentication, invalid/private fields, deletion and retention. Android redaction is checked separately by `scripts/tests/test_s10_telemetry.py`.
