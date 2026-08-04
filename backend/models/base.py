"""SQLAlchemy 声明式基类 + UUID 工具"""

import uuid

from sqlalchemy import DateTime, func, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


def gen_uuid():
    """MySQL 兼容: 用 Python uuid4 生成, 存为 CHAR(36)"""
    return str(uuid.uuid4())


def uuid_pk():
    """MySQL 主键: CHAR(36) 存储 UUID"""
    from sqlalchemy import String
    return mapped_column(String(36), primary_key=True, default=gen_uuid)
