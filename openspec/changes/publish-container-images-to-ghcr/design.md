# Design

## Context

The existing yfinance workflow only builds when Docker Hub credentials are present, logs into Docker Hub, and pushes `latest` plus the yfinance version tag. `docker-compose.yml` uses a local image name and includes a build context, so deployment instructions currently build locally. See `proposal.md` and `specs/container-image-publishing/spec.md` for the desired behavior.

## Goals / Non-Goals

**Goals:**

- Make GHCR publication the required outcome of each qualifying image build.
- Keep Docker Hub as a separately reported optional mirror.
- Let production deployments select the prebuilt GHCR image, while preserving local builds.
- Keep registry credentials in GitHub secrets or the built-in `GITHUB_TOKEN` and out of workflow output.

**Non-Goals:**

- Changing image contents, application dependencies, or build triggers beyond what is needed to remove the Docker Hub credential gate.
- Removing Docker Hub tags or breaking current Docker Hub consumers.
- Automatically changing GHCR package visibility or access policy through an external account API.

## Decisions

### Publish GHCR first with the workflow token

Give the image workflow `packages: write` permission and authenticate to GHCR using the run's `GITHUB_TOKEN`. Build and publish `latest` and the current yfinance version tag to the repository owner's lowercase GHCR namespace. A missing Docker Hub secret must not skip the build or GHCR push.

**Alternative considered:** Keep Docker Hub credentials as the build gate and add a second tag. This still makes Docker Hub a single point of failure.

### Mirror from the completed GHCR image to Docker Hub

Build the application image once and publish it to GHCR as the authoritative image. If Docker Hub credentials exist, copy the GHCR manifests and layers to the Docker Hub tags as a separate optional step. Report mirror failures separately and preserve a successful GHCR result. This avoids rebuilding different image bytes for each registry.

**Alternative considered:** Include both registries in one build-and-push action. That couples workflow success to both registry pushes and can obscure which registry succeeded.

### Select the deployment image through Compose interpolation

Add an `AI_HEDGE_FUND_IMAGE` override to `docker-compose.yml` and document the GHCR image reference. Preserve the local `build` definition for development. For production, the documented pull-and-run sequence must use the selected image with Compose's no-build option so operators do not need a source checkout or local build. Set GHCR package visibility to public outside the workflow if anonymous pulls are desired; document authentication for private packages.

**Alternative considered:** Replace the local Compose build with a fixed GHCR reference. That would make local development less convenient and reduce deployment flexibility.

### Keep tag and release mapping stable

Use the existing build triggers and version source. Publish `latest` and the current yfinance version tag to GHCR, then mirror those exact references to Docker Hub. A forced rebuild republishes the current pair without inventing a new version.

## Risks / Trade-offs

- [GHCR's first package may be private by default] → Document the package visibility step and show authenticated and anonymous pull paths.
- [The built-in token may lack package access because repository or organization settings restrict it] → Fail the required GHCR publication clearly and document the minimum workflow permission and package linkage requirements.
- [Docker Hub mirroring may fail after GHCR succeeds] → Treat mirror failure as a separate warning and keep the GHCR image available.
- [Lowercase namespace and tag drift can break pulls] → Normalize the repository owner, use one version source, and verify published references in CI.
- [Compose may still build when a build section is present] → Document and verify the prebuilt deployment path with `--no-build`; retain local build instructions separately.

## Migration Plan

1. Add GHCR package permissions and authentication to the existing image workflow; remove Docker Hub credentials from the build decision.
2. Publish GHCR `latest` and version tags on existing qualifying events.
3. Add the optional Docker Hub mirror step after GHCR publication.
4. Add an image-reference override to Compose and document GHCR pull/authentication and local-build paths.
5. Update `CHANGELOG.md` and validate a GHCR-only workflow run before relying on the registry in deployment instructions.

If GHCR publishing has a release-blocking problem, revert the workflow and Compose changes. Existing Docker Hub images remain available for rollback.
