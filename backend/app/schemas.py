"""Pydantic request/response models."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BaseDefinitionIn(BaseModel):
    metric_key: str = Field(min_length=1, max_length=64)
    metric_name: str = Field(min_length=1, max_length=64)
    grain: str
    time_field: str
    aggregation: Literal["sum", "count"]
    source_table: str
    amount_field: str


class DerivedDefinitionIn(BaseModel):
    metric_key: str = Field(min_length=1, max_length=64)
    metric_name: str = Field(min_length=1, max_length=64)
    formula: str


class DefinitionSetIn(BaseModel):
    """Full snapshot of a draft version's definitions."""
    base: List[BaseDefinitionIn]
    derived: List[DerivedDefinitionIn]


class DefinitionOut(BaseModel):
    metric_key: str
    metric_name: str
    kind: Literal["base", "derived"]
    grain: Optional[str] = None
    time_field: Optional[str] = None
    aggregation: Optional[str] = None
    source_table: Optional[str] = None
    amount_field: Optional[str] = None
    formula: Optional[str] = None


class VersionOut(BaseModel):
    version_id: str
    label: str
    status: Literal["draft", "published"]
    created_at: str
    published_at: Optional[str] = None


class QueryIn(BaseModel):
    version_id: str
    start_date: str
    end_date: str
    store_id: Optional[str] = None  # null = all stores


class CompareIn(BaseModel):
    left_version_id: str
    right_version_id: str
    start_date: str
    end_date: str
    store_id: Optional[str] = None


class DrillIn(BaseModel):
    version_id: str
    date: str
    store_id: str
