# Cash Flow policy work in progress

Implementation was stopped at the user's request. This branch is an incomplete
review draft and is not ready to merge, migrate, or deploy.

The current edits sketch company policy versions for interest and tax cash flow,
evidence-backed noncash debit/credit pairings, disposal-result and policy
adjustment rules, and links from Cash Flow snapshots to noncash disclosures.
They reuse the existing Cash Flow application service and relational models.

Required follow-up before using this branch:

- Complete and review the application rules, provenance, and snapshot integration.
- Add the database migration and model registry wiring. Migration 030 was reserved
  for this work but has not been created. Coordinate its predecessor with the
  Tax and Asset branches before creating it.
- Review policy effective dates and version compatibility, noncash completeness,
  disposal journal classification, permissions, isolation, and idempotency.
- Add focused Golden and PostgreSQL integration tests and run verification.
- Implement the remaining Report Center Cash Flow export separately.

No tests, lint, type checks, migration checks, or runtime verification were run
for these edits. No frontend changes were made. SCE and Notes remain unavailable;
their event, registry, validation, and approval requirements are not implemented.
Issue #87 remains open.

Design SSOT was read as reference and was not modified.
