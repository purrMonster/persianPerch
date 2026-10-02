# ADR 0005 - CSRF protection for the page's Acknowledge (perch has no session)

- Status: accepted - 2026-10-02 - M3 (meow)
- Context: 05 plan A11 ("`POST /ack/{litterId}` behind Authelia, with a CSRF token"), test S9.

## Context

Acknowledge is the first POST a person makes on perch. Authelia is the login: Traefik forwards every
request with the user's cookie, and perch itself has no sessions, no cookies and no database of users.
The classic defence (a token stored in the session) therefore has nothing to store it in. The action is
small (it stops the repeats of one alert and writes nothing else), but "a page on another address can
silence my alarm" is exactly the thing to rule out.

## Options

| Option | For | Against |
|---|---|---|
| A. Add a session cookie to perch | textbook | new state, new cookie handling behind a proxy, for one button |
| B. Only check `Origin` / `Sec-Fetch-Site` | no token | one header check is the whole defence; a missing header must mean refuse |
| C. **Both: a same-origin check, and a stateless signed form token** | two independent checks; no session | the token is not tied to a person (see below) |
| D. Custom header only (`X-Requested-With`) | easy for htmx | a browser sends it only from script; the no-JavaScript form would break |

## Decision

**C.**
1. **Same origin.** Refuse (403) unless the request proves it came from perch's own page: `Sec-Fetch-Site`,
   when present, must be `same-origin`; `Origin`, when present, must have the request's own `Host`; with
   neither header, refuse. Every browser sends at least one of them on a POST.
2. **Form token.** `csrf = <expiry>.<HMAC-SHA256(key, "csrf1\n" + litterId + "\n" + expiry)>`, key
   `PERCH_ACK_SECRET` (a random per-process key when it is unset), valid 6 hours, **bound to the litter**,
   minted at render and put in a hidden field of the Acknowledge form. The 30 s htmx refresh re-renders it,
   so an open tab always has a fresh one. It is compared in constant time. A different prefix from the push
   token's means neither can stand in for the other.
3. The form is a normal `<form method="post">`: with JavaScript off it posts and gets a 303 back to `/`;
   with htmx (`hx-post`, ADR 0003's config: no eval, no `hx-on`) the form is replaced by one line.
4. Errors are pages (docs/06 rule 19): a refused ack shows "Not allowed" and what to do.

## Consequences

- The token proves "this came from a perch page rendered by this perch", not "from this person": anyone
  who can load the overview can mint one, but they could already press the button. A page on another
  origin can neither read the token (same-origin policy) nor pass the origin check.
- Nothing is stored for it. Restarting perch with no `PERCH_ACK_SECRET` set invalidates open forms; a
  reload fixes it.
