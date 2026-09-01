# Solution — release-gates

The extension adds one pure evaluator and keeps storage concerned only with locating
the environment-specific definition.

## Explicit precedence

Evaluation proceeds in a fixed order: emergency disable, workspace allowlist, rules in
their stored order, percentage rollout, then default. Each return includes a reason and
the matching rule ID where applicable, so production decisions are explainable.

## Stable percentage cohorts

The evaluator hashes `gate_key:workspace_id` with SHA-256, converts a fixed portion of
the digest into one of 10,000 buckets, and compares it with `percentage * 100`. This is
stable across processes, salted per gate, and monotonic: increasing the threshold can
only add workspaces.

Python's built-in `hash()` is intentionally unsuitable because string hashing is
randomized between interpreter processes. A random draw per evaluation is worse: the
same workspace can switch behavior on consecutive requests.

## Interview talking points

- Precedence is product policy and should be visible in one evaluation pipeline.
- Immutable definitions and a pure evaluator make behavior repeatable and cacheable.
- Cohort identity needs a stable targeting key; missing keys should fail to an
  explainable default.
- Evaluation metadata is essential for debugging rollout behavior safely.
