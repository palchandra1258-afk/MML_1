# 09 — Security and multi-user readiness

## Current boundary

Student Studio uses the hard-coded `studio-local-demo` profile. It is explicitly a local demonstration profile, not authentication. Routes accept no authenticated principal, and methods scope data to this constant. This is useful for local isolation from EdNet IDs, but it is not multi-user authorization and must not be represented as such.

The F9 profile has no FK from its `profile_id` values to an identity provider. Some demo-specific references are scoped in query predicates, while ownership is effectively global to the one profile. Research artifact/trajectory routes use `learner_references` and are a distinct namespace; they do not make Studio multi-user.

## Required before real multi-user deployment

- Add an authentication/session mechanism and derive learner ID only from the verified server principal, never request body/query parameters.
- Every plan, version, session, progress, attempt, tutor-history and evidence operation must enforce owner scoping in its SQL predicate and service layer. Use composite foreign keys/constraints where feasible to prevent plan/profile/session/attempt cross-linking.
- Return non-enumerating 404 for cross-owner IDs; test horizontal privilege escalation on every read and write route. Ensure background workers carry authenticated ownership context safely.
- Review tenant/guardian/educator access separately; define consent, retention, deletion/export, audit history, and breach response. Do not make canonical evidence mutable to satisfy plan lifecycle.
- Protect student answers, goals, tutor content and evidence from logs/analytics; encrypt transport and storage according to deployment threat model; restrict database/backup access; define key management and retention.
- Add rate limiting/abuse controls, CSRF/session protections appropriate to deployment, and per-learner quotas. Current AI rate limit is process-local and keyed by client IP; it is not user quota or durable coordination.
- Resolve demo profile migration and identity mapping as a deliberate, reversible data decision; do not silently convert research learner IDs to accounts.

No authentication, user isolation, or schema changes were implemented in this audit.
