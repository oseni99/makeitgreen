# Solution — token-auth-api (JavaScript)

Substring checks turned authentication and authorization into fuzzy searches.
Compare the bearer token with `===` and check capability membership with
`Set.has()`. Both credentials and permissions are exact identifiers; accepting
a fragment silently expands access.
