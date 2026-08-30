import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import GUID

# Explicit naming convention so Alembic autogenerate produces stable, predictable
# constraint/index names instead of dialect-default ones that vary and are hard to diff.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    # Python-side default (not just server_default): SQLite's server-side CURRENT_TIMESTAMP
    # only has second resolution, which made ORDER BY created_at non-deterministic for rows
    # inserted within the same test. A client-computed, timezone-aware, microsecond-resolution
    # value avoids that on every backend. server_default in the migration stays as a DB-level
    # fallback for rows inserted outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
