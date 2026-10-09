from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, text
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Versioned:
    version: Mapped[int] = mapped_column(server_default=text("1"))
