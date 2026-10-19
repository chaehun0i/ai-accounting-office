"""Deterministic facts used to gate and revalidate role changes."""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from app.accounting.control_accounts.domain.roles import ROLE_ACCOUNT_TYPE, ControlAccountRole


@dataclass(frozen=True)
class ImpactFact:
    code: str
    subject: str
    count: int
    blocking: bool


@dataclass(frozen=True)
class ImpactAssessment:
    facts: tuple[ImpactFact, ...]
    digest: str
    blocking: bool


_REFERENCE_CODES = (
    "POSTED_JOURNAL",
    "AR_REFERENCE",
    "AP_REFERENCE",
    "BANK_REFERENCE",
    "CARD_REFERENCE",
)


def assess_impact(
    repository: Any,
    company_id: UUID,
    role: str,
    current_account_id: UUID | None,
    target_account_id: UUID,
) -> ImpactAssessment:
    facts: list[ImpactFact] = []
    expected_type = ROLE_ACCOUNT_TYPE[ControlAccountRole(role)]
    mapping = repository.mapping(company_id, role)
    account = repository.account(company_id, target_account_id)
    facts.append(ImpactFact("MAPPING_VERSION", role, mapping.version if mapping else 0, False))
    facts.append(
        ImpactFact("TARGET_MISSING", str(target_account_id), int(account is None), account is None)
    )
    if account is not None:
        facts.extend(
            (
                ImpactFact("TARGET_VERSION", str(target_account_id), account.version, False),
                ImpactFact(
                    "TARGET_INACTIVE",
                    str(target_account_id),
                    int(account.status != "ACTIVE"),
                    account.status != "ACTIVE",
                ),
                ImpactFact(
                    "TARGET_NOT_POSTABLE",
                    str(target_account_id),
                    int(not account.posting_allowed),
                    not account.posting_allowed,
                ),
                ImpactFact(
                    "TARGET_TYPE_MISMATCH",
                    str(target_account_id),
                    int(account.account_type != expected_type),
                    account.account_type != expected_type,
                ),
            )
        )
    collisions = sum(
        1
        for value in repository.mappings(company_id)
        if value.role != role and value.account_id == target_account_id
    )
    facts.append(
        ImpactFact("OTHER_ROLE_COLLISION", str(target_account_id), collisions, collisions > 0)
    )
    for subject, account_id in (("CURRENT", current_account_id), ("TARGET", target_account_id)):
        if account_id is None:
            continue
        for code in _REFERENCE_CODES:
            count = repository.reference_count(code, company_id, account_id)
            # Existing postings and subledger/reconciliation references make a
            # role reassignment unsafe. Target usage is visible and digest-bound.
            blocking = subject == "CURRENT" and account_id != target_account_id and count > 0
            facts.append(ImpactFact(code, subject, count, blocking))
    payload = {
        "company_id": str(company_id),
        "role": role,
        "current_account_id": str(current_account_id) if current_account_id else None,
        "target_account_id": str(target_account_id),
        "facts": [asdict(fact) for fact in facts],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ImpactAssessment(tuple(facts), digest, any(fact.blocking for fact in facts))
