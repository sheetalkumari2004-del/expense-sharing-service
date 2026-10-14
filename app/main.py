from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models, schemas, services
from app.database import Base, engine, get_db


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Expense Sharing Service", lifespan=lifespan)


@app.get("/")
def welcome():
    return {
        "message": "Welcome to the Expense Sharing Service",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def get_group_or_404(db: Session, group_id: int) -> models.Group:
    group = db.get(models.Group, group_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    return group


# ---- Users ----

@app.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(body: schemas.UserCreate, db: Session = Depends(get_db)):
    user = models.User(name=body.name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A user with this name already exists")
    return user


@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(models.User).order_by(models.User.id)).all()


# ---- Groups ----

@app.post("/groups", response_model=schemas.GroupOut, status_code=201)
def create_group(body: schemas.GroupCreate, db: Session = Depends(get_db)):
    group = models.Group(name=body.name)
    db.add(group)
    db.commit()
    return group


@app.post("/groups/{group_id}/members", response_model=schemas.UserOut, status_code=201)
def add_member(group_id: int, body: schemas.MemberAdd, db: Session = Depends(get_db)):
    get_group_or_404(db, group_id)
    user = db.get(models.User, body.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    db.add(models.GroupMember(group_id=group_id, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "User is already in this group")
    return user


@app.get("/groups/{group_id}/members", response_model=list[schemas.UserOut])
def list_members(group_id: int, db: Session = Depends(get_db)):
    get_group_or_404(db, group_id)
    query = (
        select(models.User)
        .join(models.GroupMember, models.GroupMember.user_id == models.User.id)
        .where(models.GroupMember.group_id == group_id)
        .order_by(models.User.id)
    )
    return db.scalars(query).all()


# ---- Expenses ----

def expense_to_out(expense: models.Expense) -> schemas.ExpenseOut:
    return schemas.ExpenseOut(
        id=expense.id,
        description=expense.description,
        amount=services.paise_to_rupees(expense.amount_paise),
        paid_by=expense.payer.name,
        created_at=expense.created_at,
        splits=[
            schemas.SplitOut(
                user=split.user.name, amount=services.paise_to_rupees(split.amount_paise)
            )
            for split in expense.splits
        ],
    )


@app.post("/expenses", response_model=schemas.ExpenseOut, status_code=201)
def add_expense(body: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    get_group_or_404(db, body.group_id)
    member_ids = db.scalars(
        select(models.GroupMember.user_id).where(models.GroupMember.group_id == body.group_id)
    ).all()
    if not member_ids:
        raise HTTPException(400, "Group has no members")
    if body.paid_by not in member_ids:
        raise HTTPException(400, "Payer is not a member of this group")

    total_paise = services.rupees_to_paise(body.amount)
    shares = services.split_equally(total_paise, member_ids)

    expense = models.Expense(
        group_id=body.group_id,
        paid_by=body.paid_by,
        amount_paise=total_paise,
        description=body.description,
        splits=[
            models.ExpenseSplit(user_id=user_id, amount_paise=paise)
            for user_id, paise in shares.items()
        ],
    )
    db.add(expense)
    db.commit()
    return expense_to_out(expense)


@app.get("/groups/{group_id}/expenses", response_model=list[schemas.ExpenseOut])
def list_expenses(group_id: int, db: Session = Depends(get_db)):
    get_group_or_404(db, group_id)
    query = (
        select(models.Expense)
        .where(models.Expense.group_id == group_id)
        .options(
            selectinload(models.Expense.payer),
            selectinload(models.Expense.splits).selectinload(models.ExpenseSplit.user),
        )
        .order_by(models.Expense.created_at, models.Expense.id)
    )
    return [expense_to_out(e) for e in db.scalars(query).all()]


# ---- Balances & settlements ----

def load_debts(db: Session, group_id: int) -> list[tuple[int, int, int]]:
    """All (debtor, creditor, paise) entries for a group, from expenses and settlements."""
    expense_rows = db.execute(
        select(models.ExpenseSplit.user_id, models.Expense.paid_by, models.ExpenseSplit.amount_paise)
        .join(models.Expense, models.Expense.id == models.ExpenseSplit.expense_id)
        .where(models.Expense.group_id == group_id)
    ).all()
    settlement_rows = db.execute(
        select(models.Settlement.from_user, models.Settlement.to_user, models.Settlement.amount_paise)
        .where(models.Settlement.group_id == group_id)
    ).all()
    debts = [(debtor, payer, paise) for debtor, payer, paise in expense_rows]
    # Paying someone cancels what you owe them, i.e. it counts as them owing you.
    debts += [(to_user, from_user, paise) for from_user, to_user, paise in settlement_rows]
    return debts


def load_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    rows = db.execute(select(models.User.id, models.User.name).where(models.User.id.in_(user_ids)))
    return dict(rows.all())


@app.get("/groups/{group_id}/balances")
def get_balances(group_id: int, simplify: bool = False, db: Session = Depends(get_db)):
    """Who owes whom, e.g. {"Rahul": {"owes": {"Mohit": 400.0}}}.

    Default is pairwise (A owes B based on what happened between A and B).
    With ?simplify=true the same debts are collapsed into the fewest payments,
    which also removes cycles like A->B->C->A.
    """
    get_group_or_404(db, group_id)
    debts = load_debts(db, group_id)
    if simplify:
        payments = services.suggest_settlements(services.net_positions(debts))
        net = {(payer, receiver): paise for payer, receiver, paise in payments}
    else:
        net = services.net_pairwise_debts(debts)

    names = load_names(db, {uid for pair in net for uid in pair})
    balances: dict[str, dict] = {}
    for (debtor, creditor), paise in net.items():
        entry = balances.setdefault(names[debtor], {"owes": {}})
        entry["owes"][names[creditor]] = services.paise_to_rupees(paise)
    return balances


@app.post("/groups/{group_id}/settlements", response_model=schemas.SettlementOut, status_code=201)
def record_settlement(group_id: int, body: schemas.SettlementCreate, db: Session = Depends(get_db)):
    """Record that from_user paid to_user in real life."""
    get_group_or_404(db, group_id)
    if body.from_user == body.to_user:
        raise HTTPException(400, "Cannot settle with yourself")
    member_ids = set(
        db.scalars(
            select(models.GroupMember.user_id).where(models.GroupMember.group_id == group_id)
        ).all()
    )
    if not {body.from_user, body.to_user} <= member_ids:
        raise HTTPException(400, "Both users must be members of this group")

    settlement = models.Settlement(
        group_id=group_id,
        from_user=body.from_user,
        to_user=body.to_user,
        amount_paise=services.rupees_to_paise(body.amount),
    )
    db.add(settlement)
    db.commit()
    names = load_names(db, {body.from_user, body.to_user})
    return schemas.SettlementOut(
        id=settlement.id,
        from_user=names[body.from_user],
        to_user=names[body.to_user],
        amount=services.paise_to_rupees(settlement.amount_paise),
        created_at=settlement.created_at,
    )


@app.get("/groups/{group_id}/settlements/suggested", response_model=list[schemas.SuggestedPayment])
def suggested_settlements(group_id: int, db: Session = Depends(get_db)):
    """Fewest-payments plan that clears every balance in the group."""
    get_group_or_404(db, group_id)
    positions = services.net_positions(load_debts(db, group_id))
    payments = services.suggest_settlements(positions)
    names = load_names(db, set(positions))
    return [
        schemas.SuggestedPayment(
            from_user=names[payer], to_user=names[receiver], amount=services.paise_to_rupees(paise)
        )
        for payer, receiver, paise in payments
    ]
