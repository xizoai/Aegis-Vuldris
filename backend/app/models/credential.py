"""Target credential model for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TargetCredential(Base):
    """An encrypted, versioned credential scoped to a single target.

    Only one active (non-revoked) credential of a given type should exist per
    target; the credentials service enforces this invariant at creation time.
    """

    __tablename__ = "target_credentials"

    __table_args__ = (
        UniqueConstraint(
            "target_id",
            "credential_type",
            "version",
            name="uq_target_credentials_target_type_version",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    credential_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    encrypted_value: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        default=1,
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
