# Fixed asset backend: incomplete implementation snapshot

This draft preserves work stopped at the user's request on 2026-10-28. It is not ready to merge or deploy. No verification was run before publishing this snapshot, as requested.

## Included source

- Framework-free fixed asset, company policy, depreciation run and line entities.
- Decimal straight-line cumulative depreciation calculation with explicit monthly/daily and acquisition-month inputs.
- Partial registration service requiring a posted acquisition Journal, and a calculation service intended to generate draft Journals for the existing independent approval workflow.
- Relational ORM models, repository/unit-of-work scaffolding, and API request/response definitions.

## Required continuation

- Review and complete service invariants, including prospective policy changes, lock ordering, provenance, reversal handling, and source integrity at approval/posting.
- Wire services, routes, model registration and explicit role permissions. The new modules are currently not connected to the application.
- Add the reserved 029 migration only after the Tax 028 migration is available and its exact revision ID is confirmed. No migration is included in this draft, and existing database schemas remain unchanged.
- Add the ASSET Journal source through the Core schema and validation boundary; protect generated draft Journals against manual edits and verify source links. The current service references this not-yet-supported source.
- Add focused domain, API, permission, database, migration and approval/posting tests. Run lint and type checks and inspect migration parity before marking the PR ready.
- Complete fixed asset events, disposal, impairment and GL reconciliation in subsequent reviewed work.

Inventory, allowance/bad-debt and manufacturing/CVP cost modules are not included. Their milestones remain open. No frontend or Design SSOT file was changed.

The PR targets `main`. Before adding migration 029, incorporate the reviewed Tax 028 branch or its merged main revision so the Alembic history remains linear. Do not merge or enable auto-merge on this draft.
