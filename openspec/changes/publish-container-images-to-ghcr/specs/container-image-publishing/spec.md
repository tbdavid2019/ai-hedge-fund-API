# Spec Delta

## Purpose

Publish versioned application container images to GitHub Container Registry so deployments have a GitHub-hosted image source that does not require Docker Hub credentials. Docker Hub remains available as an optional mirror for existing users.

## ADDED Requirements

### Requirement: Qualifying builds publish to GHCR
For every workflow event that produces an application image, the system MUST publish the image to `ghcr.io/<repository-owner>/ai-hedge-fund-api` using GitHub Actions package permissions. Publishing to GHCR MUST NOT depend on Docker Hub credentials.

#### Scenario: Build runs without Docker Hub credentials
- **WHEN** a qualifying build runs and Docker Hub credentials are absent
- **THEN** the workflow MUST still build and publish the image to GHCR
- **AND** the workflow MUST report Docker Hub publishing as skipped

#### Scenario: GHCR publication fails
- **WHEN** a qualifying build cannot publish to GHCR
- **THEN** the workflow MUST report the build as failed
- **AND** MUST NOT report the image as successfully published

### Requirement: Registry tags identify the same release
The workflow MUST publish both a moving `latest` tag and the current version tag to GHCR. When Docker Hub credentials are configured, the workflow MUST publish the corresponding tags there for the same application build.

#### Scenario: Version update publishes both tags
- **WHEN** the workflow publishes an image after a yfinance version update
- **THEN** GHCR MUST contain `latest` and the version-tagged image
- **AND** any Docker Hub mirror MUST use the same two tags and image build

#### Scenario: Forced rebuild publishes current tags
- **WHEN** a workflow dispatch forces an image rebuild without a version change
- **THEN** GHCR MUST update `latest` and publish the current version tag

### Requirement: Docker Hub is an optional mirror
Docker Hub credentials MUST be optional for image publishing. When credentials are configured, the workflow MUST attempt to publish the GHCR release to Docker Hub. A Docker Hub outage or rejected push MUST NOT remove or invalidate the successfully published GHCR image.

#### Scenario: Docker Hub mirror succeeds
- **WHEN** Docker Hub credentials are configured and the mirror push succeeds
- **THEN** the workflow MUST report both registry references for the release

#### Scenario: Docker Hub mirror fails after GHCR succeeds
- **WHEN** the GHCR image is published but a Docker Hub mirror push fails
- **THEN** the GHCR image MUST remain available
- **AND** the workflow MUST report the Docker Hub mirror failure separately

### Requirement: Deployments can pull a prebuilt GHCR image
Deployment instructions MUST show how to select and pull the GHCR image without requiring a local image build. Public-package and private-package authentication requirements MUST be documented.

#### Scenario: Operator selects GHCR in Docker Compose
- **WHEN** an operator configures the GHCR image reference
- **THEN** Docker Compose MUST be able to pull and run that published image without building it locally

#### Scenario: Operator pulls a public or private package
- **WHEN** an operator follows the documented GHCR pull instructions
- **THEN** the instructions MUST state whether anonymous pull is available or GitHub Container Registry authentication is required
