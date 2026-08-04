# DEPRECATED: These Pydantic models are defined but NOT yet wired into route request/response
# validation. They serve as documentation/specification only. To activate, add them as
# type annotations to FastAPI route handlers (e.g., def create_qa(payload: QAFilters)):
#   - PaginatedResponse → return type for list endpoints
#   - PaginationParams  → query param model for paginated GET endpoints
#   - QAFilters         → query param model for QA list with filters
# TODO: Wire into route handlers once all endpoints are migrated to typed validation.

"""Pydantic schemas — 请求/响应模型 (deprecated, see comment above)"""

from pydantic import BaseModel, Field
from typing import TypeVar, Generic

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class QAFilters(PaginationParams):
    status: str = Field(default="all")
    phase: str = Field(default="all")
    type: str = Field(default="all")
    difficulty: str = Field(default="all")
    search: str = Field(default="")
