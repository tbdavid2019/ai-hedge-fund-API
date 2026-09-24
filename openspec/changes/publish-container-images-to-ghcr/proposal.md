# Proposal

## Why

The current automated image workflow depends on Docker Hub credentials and only publishes there, so a missing or unavailable Docker Hub account blocks image distribution. Publishing the same versioned image to GitHub Container Registry gives users a first-party pull source while preserving Docker Hub as an optional mirror.

## What Changes

- Publish `latest` and version-tagged images to GHCR on the existing image-build triggers, using the workflow's `GITHUB_TOKEN` with package-write permission.
- Keep Docker Hub publishing when its credentials are configured, but do not make those credentials a prerequisite for building or publishing to GHCR.
- Let deployments select a prebuilt GHCR image through Docker Compose while preserving local build usage.
- Update `README.md`, `AGENTS.md`, and `CHANGELOG.md` with registry selection, pull, authentication, and image-tag guidance.

## Capabilities

### New Capabilities

- `container-image-publishing`: Build and publish version-consistent container images to GHCR and optionally Docker Hub.

### Modified Capabilities

None.

## Impact

- `.github/workflows/yfinance-auto-update.yml` for registry authentication, build gating, tagging, and publishing.
- `docker-compose.yml` for configurable selection of the published GHCR image.
- `README.md` and `AGENTS.md` for operator and developer instructions.
- `CHANGELOG.md` for the release record.
- No application API or runtime dependency changes.
