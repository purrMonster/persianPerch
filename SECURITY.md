# Security

persianPerch is a private watcher for one household's home lab, published so its design and code can be
read. It is not a product with users, so there is no support promise, but problems are welcome.

## Reporting a problem

Use GitHub's **private vulnerability reporting** on this repository (Security → Report a vulnerability),
not a public issue. If you found a credential in the repository or its history, say where; it will be
rotated, not just deleted.

## What is public here on purpose

- The fleet's layout: node names, their roles and their private LAN addresses (RFC 1918, not reachable
  from the internet), as in the public fleet repo `purrMonster/purrbrews-containers`.
- How access works: which routes skip the single sign-on and why (`integration/ROLLOUT.md`). perch's
  safety does not depend on those details staying secret.
- The owner's GitHub user name and the commit identity the agent rules require.

## What never is

Secret values (tokens, passwords, keys, ping URLs, ntfy topics), the real domain (`${DOMAIN}` stands for it),
and personal data. `secrets.env` lists keys with no values. Tests S5, S6 and S10 (`tests/test_repoHygiene.py`)
and the gitleaks scan in CI (`.gitleaks.toml`) check every tracked file and every commit.
