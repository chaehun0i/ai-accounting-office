"""Alembic과 조립 계층에서만 업무 메타데이터를 명시적으로 등록합니다."""

from app.identity.sessions.infrastructure.models import (
    IdentitySecurityEventModel,
    RefreshSessionModel,
)
from app.identity.users.infrastructure.models import UserModel

__all__ = ["UserModel", "RefreshSessionModel", "IdentitySecurityEventModel"]

from app.companies.infrastructure.models import (
    CompanyModel,
    InvitationModel,
    MembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    TenantModel,
)

__all__ += [
    "CompanyModel",
    "TenantModel",
    "RoleModel",
    "PermissionModel",
    "RolePermissionModel",
    "MembershipModel",
    "InvitationModel",
]

# 회계 Master 모델은 명시적으로 등록하고 import 시 연결하지 않습니다.
from app.accounting.accounts.infrastructure import models as accounts_models  # noqa: F401, E402
from app.accounting.periods.infrastructure import models as periods_models  # noqa: F401, E402
from app.accounting.sequences.infrastructure import models as sequences_models  # noqa: F401, E402
from app.accounting.settings.infrastructure import models as settings_models  # noqa: F401, E402
from app.accounting.templates.infrastructure import models as templates_models  # noqa: F401, E402
from app.evidence.infrastructure import models as evidence_models  # noqa: F401, E402
from app.intake.infrastructure import models as intake_models  # noqa: F401, E402
from app.master_data.counterparties.infrastructure import (  # noqa: E402
    models as counterparties_models,  # noqa: F401, E402
)
from app.master_data.payment_terms.infrastructure import (  # noqa: E402
    models as payment_terms_models,  # noqa: F401, E402
)
from app.onboarding.infrastructure import models as onboarding_models  # noqa: F401, E402

# 파일과 증빙·인테이크 메타데이터를 등록합니다.
from app.storage.infrastructure import models as storage_models  # noqa: F401, E402
