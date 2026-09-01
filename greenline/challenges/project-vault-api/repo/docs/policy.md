# Project vault access policy

Authentication supplies a verified user and workspace.

| Role | List/read | Rename | Delete |
|---|---:|---:|---:|
| Project viewer | yes | no | no |
| Project editor | yes | yes | no |
| Workspace administrator | yes | yes | yes |

All access is scoped to the authenticated workspace and the project named in the URL.
A document from another project must never satisfy that URL, even when its ID is valid.
