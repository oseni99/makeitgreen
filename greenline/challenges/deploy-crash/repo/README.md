# Notifications service boot incident

The notifications service is built as a small package under `deploy/`.
The production process manager runs `python -m deploy`. That entrypoint calls
`deploy.bootstrap.boot()`, which resolves a configuration module and constructs
the service.

Release `2026.08.30` renamed the default configuration module during a cleanup.
CI exercises explicit configuration overrides, while production normally uses
the default. The rollout is now crash-looping.

Start with the readonly evidence in `logs/`, then inspect the boot path. Keep
the explicit `APP_CONFIG_MODULE` override working; operators use it for staging
and emergency configuration.
