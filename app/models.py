from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# All money is stored as integer paise (1 rupee = 100 paise) to avoid float errors.


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint("amount_paise > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    paid_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    payer: Mapped["User"] = relationship()
    splits: Mapped[list["ExpenseSplit"]] = relationship(order_by="ExpenseSplit.user_id")


class ExpenseSplit(Base):
    """Who owes how much for one expense, frozen at the time it was created."""

    __tablename__ = "expense_splits"
    __table_args__ = (UniqueConstraint("expense_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount_paise: Mapped[int] = mapped_column(Integer)

    user: Mapped["User"] = relationship()


class Settlement(Base):
    """A real payment: from_user paid to_user, reducing what from_user owes."""

    __tablename__ = "settlements"
    __table_args__ = (CheckConstraint("amount_paise > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    from_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
