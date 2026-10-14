from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class UserCreate(BaseModel):
    name: Name


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class GroupCreate(BaseModel):
    name: Name


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class MemberAdd(BaseModel):
    user_id: int


Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class ExpenseCreate(BaseModel):
    group_id: int
    paid_by: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)  # in rupees
    description: Description


class SplitOut(BaseModel):
    user: str
    amount: float


class ExpenseOut(BaseModel):
    id: int
    description: str
    amount: float
    paid_by: str
    created_at: datetime
    splits: list[SplitOut]


class SettlementCreate(BaseModel):
    from_user: int  # the person paying
    to_user: int  # the person being paid
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)  # in rupees


class SettlementOut(BaseModel):
    id: int
    from_user: str
    to_user: str
    amount: float
    created_at: datetime


class SuggestedPayment(BaseModel):
    from_user: str
    to_user: str
    amount: float
