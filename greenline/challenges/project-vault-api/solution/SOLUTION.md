# Solution — project-vault-api

Authentication was working, but two independent authorization boundaries were not.

## Resource scope

The broken store looked up a document by globally unique ID and ignored the workspace
and project from the authorized URL. A valid ID could therefore escape its container.
The fixed repository methods require all three identifiers for reads and mutations and
return no document when any part of the scope disagrees.

## Capability checks

Project membership does not imply every capability. The fixed handlers implement the
documented matrix:

- viewers: list and read;
- editors: list, read, and rename;
- workspace administrators: all operations, including deletion.

Checks happen before document serialization or mutation, so denied responses cannot
contain protected values and denied writes are no-ops.

## Interview talking points

- Authentication answers who the caller is; authorization answers what that caller may
  do to this particular resource.
- Scope database queries by tenant and parent resource rather than retrieving globally
  and filtering later.
- Test horizontal isolation, parent-child relationships, and capability levels
  independently.
- A `403` body must not become a side channel for the data it protects.
