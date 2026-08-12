# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not
open a public issue containing credentials or an unpatched exploit.

## Credential handling

The scanner reads provider credentials only from environment variables. Never
commit `.env`, downloaded workflow artifacts containing private data, or API
keys. GitHub Actions receives credentials through encrypted repository secrets
and has read-only repository permissions.
