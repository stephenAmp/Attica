import uuid as uuid_lib
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy import Uuid, ForeignKey, DateTime, String, Integer, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

from app.storage.postgres import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None ] = mapped_column(String(100), nullable=True)


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    full_name: Mapped[str] = mapped_column(String(100), nullable = False)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default = True)
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)


class UserTenants(Base):
    __tablename__="user_tenant"

    user_id : Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user.id"), primary_key=True, nullable=False)
    tenant_id : Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant.id"), primary_key=True, nullable=False)
    role_id: Mapped[uuid_lib.UUID] = mapped_column(
    ForeignKey("role.id"), nullable=False
)


class Role(Base):
    __tablename__ = "role"

    id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, nullable=False, default=uuid_lib.uuid4)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

class Permission(Base):
    __tablename__ = "permission"

    id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True),primary_key=True, nullable=False, default=uuid_lib.uuid4)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)


# Permission each role in a tenant has
class RolePermission(Base):
    __tablename__="role_permission"

    role_id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("role.id"), primary_key=True, nullable=False)
    permission_id: Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("permission.id"), primary_key=True, nullable=False)


class Interaction(Base):
    __tablename__ = "interaction"

    id:Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    tenant_id:Mapped[uuid_lib.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), nullable=False, default = lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_token: Mapped[int] = mapped_column(Integer, nullable=False)
    output_token: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[str]  = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)