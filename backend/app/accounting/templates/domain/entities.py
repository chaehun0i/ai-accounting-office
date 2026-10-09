from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Template:
    id: UUID
    template_code: str
    name: str
    version: int
    status: str
    valid_from: date


@dataclass(frozen=True, kw_only=True)
class TemplateAccount:
    id: UUID
    coa_template_id: UUID
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    parent_code: str | None
    posting_allowed: bool
    display_order: int
    is_contra: bool = False
