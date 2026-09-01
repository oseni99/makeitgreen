# Solution — deploy-crash

## Root cause

The release evidence points to configuration resolution, not the health check:

- the process exits before health probing;
- the traceback names `deploy.settings` as missing;
- `APP_CONFIG_MODULE` is unset in production;
- the release note says `deploy.settings` was renamed to `deploy.config`.

`boot()` correctly honors an explicit module override, which is why the CI path
and staging checks were green. Production follows `DEFAULT_CONFIG_MODULE`, and
that constant still referenced the removed name. The import lives inside
`boot()`, so the incident is reproduced as a normal failing test rather than a
pytest collection failure.

The regression suite also launches the recorded production command,
`python -m deploy`, in a subprocess. Its real `deploy.__main__` entrypoint reaches
the same stale default, while pytest captures the crash and reports an ordinary
test failure.

## Fix

Update the default to the module that actually ships:

```python
DEFAULT_CONFIG_MODULE = "deploy.config"
```

Keep explicit overrides strict. Catching `ModuleNotFoundError` and silently
falling back would conceal an operator typo and could boot with the wrong
configuration—the same failure mode in a quieter form.

## Interview talking points

- **Evidence first:** establish whether the process reached application startup,
  health checks, or request handling before changing code. Here the traceback
  and environment snapshot narrow the path to one default.
- **CI/prod parity:** CI covered the explicit override but not the production
  default. Add a boot smoke test with the production-shaped environment.
- **Fail loud on explicit configuration:** defaults may be deliberate, but an
  explicitly named missing module is a configuration error, not permission to
  guess.
- **Safer deploys:** retain the previous revision until new instances pass
  readiness, and make the process-manager boot command part of release smoke
  testing.
- **Import placement:** a runtime import makes configuration selectable, but
  every supported branch still needs a boot-level test. A stale top-level import
  would fail test collection and provide a worse developer feedback loop.
