# ADR 0007 - binocs reads upstream releases through the registries' OCI API, and only when switched on

- Status: accepted - 2026-10-03 - M4 (the owner's task named the three registries; the API choice and the
  default are the agent's, recorded here for the owner to overrule)
- Context: 05 plan M4 ("upstream releases, weekly, earTwitch only"), design plan 4.6.

## Context

For every image pinned in the fleet repo's compose files binocs asks "is a newer release out?", anonymously, from
cellar, once a week. The fleet pins about 45 images on Docker Hub, `ghcr.io` and `lscr.io`. Nothing in this repository may
ever make a real registry request in a test (the owner's rule for M4), and perch must not hammer a public service.

## Options for Docker Hub

| Option | For | Against |
|---|---|---|
| **A. The registry's own API** (`registry-1.docker.io`, anonymous pull token from `auth.docker.io`, `GET /v2/<name>/tags/list`) | one code path with ghcr.io; the documented way an anonymous client reads a public image; tag lists are complete | lexical order, so the whole list is read (up to 20 pages of 1000) |
| B. Docker Hub's REST API (`/v2/namespaces/<ns>/repositories/<repo>/tags`) | pages by date | the OpenAPI spec Docker publishes (read 2026-10-03) declares it bearer-authenticated and documents only `page` and `page_size` (no ordering) for it: nothing promises anonymous access, and a feature that depends on an unpromised behaviour breaks on a Tuesday |
| C. GitHub releases of each project | real "release" semantics | needs an image-to-repository map for 50 images; 60 anonymous requests an hour |

**A.** ghcr.io and `lscr.io` (a name for `ghcr.io/linuxserver/...`, per LinuxServer) use the same flow with their
own token service. A token challenge is followed only to the registry's own token host (`ghcr.io`, `auth.docker.io`).

## What counts as a release

`[v]MAJOR.MINOR.PATCH` (three or more numbers) with an optional flavour (`-alpine`, `-omnibus`), same flavour and
same number of parts; a LinuxServer `-lsNNN` rebuild counter is ignored (a rebuild is not a release). A newer one is an
earTwitch state `binocs:release/<repo>` that meow lists in the morning digest, **never** a hiss, and it never moves the
fleet badge. Digest pins, `stable`, `latest`, `main`, a local build and line pins (`postgres:16`, `v1.10`) can't be
compared; they are counted as "can't be compared", never guessed.

## Rate limits

Docker documents `429` with `Retry-After` and an abuse limit per IP address. perch lists each repository once a week,
pauses a second between repositories, and a `429` from any registry stops the run: the repositories already read keep
their answer, and the run resumes when the registry's `Retry-After` has passed (not a week later).

## Off unless switched on

`PERCH_BINOCS_RELEASES_EVERY` now defaults to **off (0)**; the compose file M6 prepares sets `7d`. The dev plan's
default was 7 days. The reason: a perch that starts with its defaults (a developer's run, the UI test containers) would
otherwise contact public registries by itself. The setting stays in `secrets.env` as an empty key (S5) with the note.

## Consequences

Two hostnames join the S6 allow-list, each with its reason: `ghcr.io` and `lscr.io`. (`*.docker.io` was already there.)
`registries.py` is the one module that knows the registries, as `komodo.py` is for Komodo.
