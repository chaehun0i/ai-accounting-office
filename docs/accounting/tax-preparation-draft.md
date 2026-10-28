# Tax preparation backend draft

Status: incomplete draft, not deployment-ready. Implementation was stopped at the user's request on 2026-10-28 so the current work could be reviewed in a draft PR.

## Implemented draft surface

The backend adds `/tax/profiles`, `/tax/periods`, VAT and withholding preparation inputs under `/tax/periods/{period_id}`, and `/tax/periods/{period_id}/preparation`. It reuses the existing company-scoped tax permissions and CSRF dependency. Write commands require an Idempotency-Key and record a request fingerprint and relational result reference.

The proposed relational models cover effective-dated profiles, independent tax periods, VAT treatment revisions, withholding revisions, and command receipts. Company-scoped composite foreign keys connect facts to transactions, evidence, counterparties, and periods. Corrections create another fact revision; aggregates select the latest revision for each transaction.

Preparation computes Decimal totals from entered facts and reports missing profiles, evidence, VAT classifications, unresolved deductions, and changed source transactions. User-supplied rule references remain unverified. Readiness always blocks filing pending verified rules, required forms, accounting acceptance, and reviewer approval. No statutory rates or deadlines are supplied and there is no filing endpoint.

## Remaining work before implementation review can pass

- Migration 028 was reserved but **has not been created**. Existing databases cannot serve these endpoints until a reviewed migration is added and applied.
- PostgreSQL integration coverage, migration execution, API behavior, concurrency, company isolation, and idempotency have not been verified.
- A targeted Ruff check initially found formatting and line-length errors; formatting was applied, but a clean final check has not been confirmed. Type checking was started but its result was not yet available when work stopped.
- No focused Tax tests have been added. Existing test fixture wiring alone is not verification.
- Profile overlap is rejected; ending an existing open-ended profile and activating a successor is not yet implemented.
- Approval, verified effective-dated rule registry, statutory computation, form mapping, automatic obligation/calendar generation, immutable filing snapshots, and accounting-close acceptance remain outside this draft.

The Design SSOT was read without modification. No frontend code is included. This draft does not complete the Tax milestone.
