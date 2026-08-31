import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class UserMemory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user_memories"
    __table_args__ = (Index("ix_user_memories_tenant_id_user_id", "tenant_id", "user_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Traceability only, deliberately NOT a foreign key: extraction runs as a background task that
    # FastAPI doesn't guarantee runs after the triggering request's own session has committed (a
    # real race hit live — the Conversation row didn't exist yet when this tried to insert with an
    # FK to it). A soft reference avoids that timing dependency entirely; it just won't get
    # cleaned up if the source conversation is later deleted, which is fine for a "for reference
    # only" field.
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
