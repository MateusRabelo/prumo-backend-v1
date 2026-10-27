from typing import Literal, Optional
from uuid import UUID
from pydantic import Field, field_validator
from app.schemas.base import BaseModel


class ImportSelection(BaseModel):
    index: int = Field(ge=0, le=499)
    description: str = Field(min_length=1, max_length=255)
    type: Literal['RECEITA', 'DESPESA']
    category_id: Optional[UUID] = None
    remember: bool = False

    @field_validator('description')
    @classmethod
    def strip_description(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Informe um nome para o lançamento')
        return value


class ImportConfirm(BaseModel):
    preview_token: str = Field(max_length=800_000)
    reviewed: Literal[True]
    reconciliation_reviewed: bool = False
    entries: list[ImportSelection] = Field(min_length=1, max_length=500)
