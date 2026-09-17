# Tenant Runtime Environment CLI Design

## Goal

Allow operators to manage one Tenant Runtime Environment Variable scope through `swe env` commands without reading or writing local environment files directly.

## Interface

`swe env list`, `swe env set KEY VALUE`, and `swe env delete KEY` require both `--tenant-id` and `--source-id`. They use the existing global `--host` and `--port` connection settings; their fallback remains `127.0.0.1:8088`. No command-specific base URL option is added.

`list` calls `GET /api/envs` and masks non-empty values by default. `--show-values` displays the values returned by the API. `set` sends `PATCH /api/envs` with `{"values": {KEY: VALUE}}`; `delete` sends `DELETE /api/envs/{KEY}`. Success output never echoes a written value.

## Boundaries

The existing `/api/envs` HTTP contract remains unchanged. The CLI sends `X-Tenant-Id` and `X-Source-Id` headers and does not mint, store, or accept authentication tokens. When deployment-wide authentication is enabled, the service's current authentication policy remains authoritative.

CLI HTTP failures produce concise errors and exit with status 1. The command set intentionally excludes a destructive full-replacement command, remote base URL overrides, and stdin-based secret input.

## Verification

Unit tests mock the CLI HTTP client and verify the path, payload, required scope headers, masked and explicit-value list output, global host/port use, and nonzero errors.
