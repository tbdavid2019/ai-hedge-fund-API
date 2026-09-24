# Tasks

## 1. GHCR Build and Publish Workflow

- [x] 1.1 Add least-privilege `packages: write` permissions and authenticate GHCR with the workflow `GITHUB_TOKEN`; verify the workflow config authenticates and does not require Docker Hub secrets.
- [x] 1.2 Remove Docker Hub credentials from the build gate and publish the existing `latest` and yfinance version tags to GHCR on qualifying triggers; verify both GHCR tags are configured for forced rebuilds independently of Docker Hub credentials.
- [x] 1.3 Add a separate optional Docker Hub mirror step that copies the GHCR image and reports mirror failures without invalidating GHCR; verify GHCR-only, successful-mirror, and failed-mirror paths from workflow conditions and error handling.

## 2. Deployment Image Selection

- [ ] 2.1 Add an `AI_HEDGE_FUND_IMAGE` override to `docker-compose.yml` while retaining the local build path; verify Compose can pull and run the selected GHCR tag with `--no-build` and can still build locally.

## 3. Operator and Developer Documentation

- [x] 3.1 Update `README.md` with GHCR and Docker Hub image references, version tags, pull/run commands, and public/private package authentication steps; verify commands use the configured image names and do not require source builds.
- [x] 3.2 Update `AGENTS.md` with GHCR publishing behavior, image selection, workflow permissions, and the optional Docker Hub mirror; verify developer instructions no longer make Docker Hub credentials a requirement for publishing.
- [x] 3.3 Add the GHCR publishing change to `CHANGELOG.md`; verify the entry contains no credential values and matches the implemented registry behavior.

## 4. Release Verification

- [x] 4.1 Validate the workflow and Compose YAML syntax; inspect required GHCR permissions, optional Docker Hub behavior, and both registry tag patterns.
- [ ] 4.2 Run a controlled GHCR-only publish and pull using the version tag; verify the image starts with the documented Compose command and the published digest/tag is reported correctly.
