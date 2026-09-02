# Solution — token-auth-api

The authorizer used substring checks for both credentials and scopes. That
made a prefix of a valid token authenticate and allowed a scope that was only a
fragment of a real capability.

Compare the bearer token with equality and test membership in the scope set:

```python
if token == record["token"]:
    if required_scope is not None and required_scope not in record["scopes"]:
        raise Unauthorized("scope denied")
```

In a production service, keep the same exact-match boundary when looking up
hashed tokens and capabilities. Never turn authorization into a string search.
