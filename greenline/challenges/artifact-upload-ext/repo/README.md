# Artifact upload extension

`artifacts/` contains a working content-addressed store and persistent session
repository. Create `uploads/` and implement the API described in `challenge.json`.

Run `pytest -q`. Tests are local and deterministic; the repository does not need a
cloud object store or HTTP server.
