# ADR 0006 - The acknowledge button on a push: a signed, single-use token

- Status: accepted - 2026-10-02 - M3 (meow); the design is the owner's (05 plan A11, Q8 = B)
- Context: an ntfy `http` action button can only call a URL; the phone has no Authelia session, so the
  call goes to a Traefik router that bypasses Authelia for exactly one path prefix (M6-prep).

## What ntfy can do (read 2026-10-02, docs.ntfy.sh/publish; the fleet runs v2.28.0)

An `http` action is `{"action":"http","label","url","method","headers","body","clear"}`; the method
defaults to POST; up to three actions; `clear` removes the notification after the tap. That is enough for
A11: `POST {PERCH_PUBLIC_URL}/ack/t/{token}` with the token in the path, no body, no headers.

## Decision

- **Token** `<base64url litterId>.<expiry epoch>.<base64url HMAC-SHA256(PERCH_ACK_SECRET, "ack1\n" +
  litterId + "\n" + expiry)>`. It names one litter and can do exactly one thing: mark that litter
  acknowledged (stop its repeats). It cannot name another litter (the id is signed), cannot be extended
  (so is the expiry), and cannot be turned into a page's CSRF token (different prefix).
- **Single use:** the signature is stored in `ackSpent` (primary key, `INSERT OR IGNORE`, so two taps at
  once cannot both win). **24 hours** from the push, or until the litter clears (a closed litter refuses).
- **Every refusal is the same 403** with no detail, and every request counts toward **10 per minute** on
  the path (429 past that), good or bad, so a token cannot be probed or brute-forced.
- Each repeat of a hiss mints a fresh token; the button is **only on the self-hosted ntfy copy** (a third
  party would see the link) and only on a push about exactly one litter, and only when `PERCH_ACK_SECRET`
  and `PERCH_PUBLIC_URL` are both set.
- **Never logged or shown:** `scrub.py` masks the shape of a token and `/ack/t/...` links; the trail and
  the pages never hold one; `tests/ui/budget.py` looks for the real token, the secret, the ntfy token and
  the push and ping URLs in every page, perch's output and the database files.
- All token routes live under `/ack/t/`, so M6's Traefik bypass names that one prefix.

## Consequences

- Anyone holding a live push link can acknowledge that one litter once. The worst outcome is a silenced
  repeat of an alert the owner has already seen on the phone.
- Rotating `PERCH_ACK_SECRET` kills every outstanding token and form at once.
