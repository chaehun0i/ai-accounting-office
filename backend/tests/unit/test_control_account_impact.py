from types import SimpleNamespace
from uuid import uuid4

from app.accounting.control_accounts.application.impact import assess_impact


class ImpactRepository:
    def __init__(self, target_id) -> None:
        self.posted = 0
        self.target_id = target_id

    def reference_count(self, code, company_id, account_id):
        return self.posted if code == "POSTED_JOURNAL" else 0

    def mapping(self, company_id, role):
        return SimpleNamespace(account_id=self.current_id, version=2)

    def account(self, company_id, account_id):
        return SimpleNamespace(
            id=account_id,
            version=1,
            status="ACTIVE",
            posting_allowed=True,
            account_type="ASSET",
        )

    def mappings(self, company_id):
        return [SimpleNamespace(role="AR", account_id=self.current_id)]


def test_impact_digest_tracks_posted_usage_and_blocks_reassignment():
    company, current, target = uuid4(), uuid4(), uuid4()
    repository = ImpactRepository(target)
    repository.current_id = current
    initial = assess_impact(repository, company, "AR", current, target)
    assert not initial.blocking
    assert initial.digest == assess_impact(repository, company, "AR", current, target).digest
    repository.posted = 1
    changed = assess_impact(repository, company, "AR", current, target)
    assert changed.blocking
    assert changed.digest != initial.digest
    assert any(f.code == "POSTED_JOURNAL" and f.subject == "CURRENT" for f in changed.facts)
