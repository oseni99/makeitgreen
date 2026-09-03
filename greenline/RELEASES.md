# Image publication, promotion, and rollback

Greenline publishes four images to GitHub Container Registry (GHCR):

- `ghcr.io/<owner>/<repository>-control-plane`
- `ghcr.io/<owner>/<repository>-execution-worker`
- `ghcr.io/<owner>/<repository>-python-execution`
- `ghcr.io/<owner>/<repository>-node-execution`

Every default-branch release uses `sha-<full-40-character-commit>` as its
immutable tag. Deployments must ultimately record and use the corresponding
`name@sha256:<digest>` references; `staging` and `production` are promotion
handles, not immutable deployment identifiers.

## One-time GitHub configuration

1. Allow GitHub Actions to grant its job token `packages: write`,
   `attestations: write`, and `id-token: write`. Keep the workflow's default
   permission at `contents: read`.
2. Set the repository variable `VITE_CLERK_PUBLISHABLE_KEY` to the public Clerk
   key that should be compiled into the hosted frontend. Default-branch image
   builds fail closed when it is absent or malformed.
3. Create `staging` and `production` GitHub Environments. Add required reviewers,
   prevent self-review where the plan supports it, and restrict deployment
   branches to the default branch.
4. Set the environment variable `GREENLINE_PROMOTION_GATE=protected-v1` on both
   environments. The workflow fails before registry authentication if this
   deliberate-configuration marker is absent.
5. Set `GREENLINE_RELEASE_HEALTH_URL` on each environment to its public HTTPS
   `/health/release` endpoint. Configure the deployment platform to roll the
   four services when their environment tags change.
6. Ensure each GHCR package inherits access from this repository. Do not grant
   anonymous write access or use a long-lived personal access token in CI.

The marker prevents an accidentally auto-created environment from silently
becoming a release path. It does not replace required-reviewer and branch rules;
both controls must be configured in repository settings.

## Immutable publication

On a successful default-branch push, `greenline.yml` waits for backend,
frontend, content, image scan, SBOM, and deployment-smoke jobs. It then copies
the exact scanned OCI archives to GHCR without rebuilding them. Publication:

- refuses to replace an existing commit tag with a different digest;
- verifies the runnable manifest inside every attested OCI archive is the exact
  manifest that passed the vulnerability and deployment-smoke gates;
- verifies every registry digest against its scanned OCI archive;
- attaches GitHub provenance and SPDX SBOM attestations to each registry image;
- stores a `greenline-release-<commit>` manifest artifact for 90 days.

A rerun is idempotent only when all four existing tag digests match. Any
collision fails closed and requires investigation rather than tag replacement.

## Promotion

Run **Promote or roll back Greenline images** from GitHub Actions with:

- `source_sha`: the full commit SHA from a successful immutable publication;
- `target`: `staging` or `production`;
- `operation`: `promote`.

The selected GitHub Environment supplies the approval gate. The workflow checks
that all four immutable source tags exist, records each previous target digest,
copies the exact image indexes without rebuilding, and verifies that the target
digests did not change during the copy. Promotions to the same environment are
serialized. The resulting promotion record is attested and retained as an
artifact for 90 days. The immutable release manifest is attested as well.

The deployment platform must consume the four `promoted_digest` values from
that record or watch the corresponding environment tags. Configure
`GREENLINE_PYTHON_EXECUTION_IMAGE` and
`GREENLINE_NODE_EXECUTION_IMAGE` with their exact digest references, never the
mutable environment tags. Every hosted control-plane instance must receive the
image's baked-in `GREENLINE_RELEASE_SHA`; the official image sets it from the
full commit SHA at build time.

After moving the tags, the workflow polls `GREENLINE_RELEASE_HEALTH_URL`.
`/health/release` returns HTTP 200 only when the normal control-plane
dependencies are ready, and its `source_sha` must exactly match the selected
release. A generic healthy response from an old deployment does not pass.

## Rollback

Choose the last known-good commit from a release manifest or prior promotion
record. Dispatch the same workflow with that full `source_sha`, the affected
environment, and `operation: rollback`. Rollback moves all four environment tags
as one approved workflow run and records both the displaced and restored
digests. It never rebuilds an older commit.

If the workflow stops after only some tags move, rerun the same approved
operation. Each component is digest-verified and the operation is idempotent.
Do not repair a partial release by overwriting an immutable `sha-*` tag.

If exact-version readiness times out, the workflow restores all four previous
digests and fails the run. Restoration preflights the complete recovery set,
rejects unrelated concurrent tag changes, verifies every restored digest, and
is safe to rerun after a partial restoration. The rollout result and rollback
TSV are retained with the attested promotion evidence.

The first promotion to a new environment has no prior release to restore. Its
failed rollout is reported as an automatic-rollback failure without deleting
registry manifests. Bootstrap a new environment before accepting traffic, then
confirm one known-good release so every later promotion has a recovery set.

Registry promotion cannot force an unspecified hosting platform to restart.
The platform's tag watcher or deployment controller remains a required
configuration; permanent external export of release records also remains an
operations responsibility.
