# Tasks

## 1. GHCR Build and Publish Workflow

- [ ] 1.1 Add least-privilege `packages: write` permissions and authenticate GHCR with the workflow `GITHUB_TOKEN`; verify a workflow run can authenticate and publish without Docker Hub secrets.
- [ ] 1.2 Remove Docker Hub credentials from the build gate and publish the existing `latest` and yfinance version tags to GHCR on qualifying triggers; verify a forced rebuild publishes both tags when Docker Hub credentials are absent.
- [ ] 1.3 Add a separate optional Docker Hub mirror step that copies the GHCR image and reports mirror failures without invalidating GHCR; verify GHCR-only, successful-mirror, and failed-mirror outcomes.

## 2. Deployment Image Selection

- [ ] 2.1 Add an `AI_HEDGE_FUND_IMAGE` override to `docker-compose.yml` while retaining the local build path; verify Compose can pull and run the selected GHCR tag with `--no-build` and can still build locally.

## 3. Operator and Developer Documentation

- [ ] 3.1 Update `README.md` with GHCR and Docker Hub image references, version tags, pull/run commands, and public/private package authentication steps; verify commands use the published image names and do not require source builds.
- [ ] 3.2 Update `AGENTS.md` with GHCR publishing behavior, image selection, workflow permissions, and the optional Docker Hub mirror; verify developer instructions no longer make Docker Hub credentials a requirement for publishing.
- [ ] 3.3 Add the GHCR publishing change to `CHANGELOG.md`; verify the entry contains no credential values and matches the implemented registry behavior.

## 4. Release Verification

- [ ] 4.1 Validate the GitHub Actions workflow and Compose configuration; verify required GHCR permissions, optional Docker Hub behavior, and both registry tag patterns.
- [ ] 4.2 Run a controlled GHCR-only publish and pull using the version tag; verify the image starts with the documented Compose command and the published digest/tag is reported correctly.
