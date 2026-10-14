# Expense Sharing Service

A small backend for tracking shared expenses in a group (a trip, a flat) and working out who owes whom.
Built with FastAPI, SQLAlchemy and SQLite.

## Features

- Users, groups, group members
- Expenses split equally among the group, with full history
- Balances between users (pairwise, optionally simplified)
- Settlements (recording a real payment between two members)
- **Enhancement:** smart settlement suggestions (see below)
- Unit and API tests, Docker setup

Not implemented: unequal splits (the schema already supports them, see "Improvements").

## Setup

Requires Python 3.12. Run these commands in Windows PowerShell from the directory that contains `app` and `requirements.txt`.

### Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the runtime packages (`fastapi`, `uvicorn`, `sqlalchemy`) plus `pytest` and `httpx`.

If PowerShell blocks the activate script, allow it for the current window and run the activate command again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Database

SQLite is the default. The connection string is `DATABASE_URL`, which defaults to `sqlite:///./expense_sharing.db` (a file in the current directory). Tables are created on startup.

To point at a different file for the current PowerShell session:

```powershell
$env:DATABASE_URL = "sqlite:///./expense_sharing.db"
```

An absolute path uses the drive letter after three slashes, for example `sqlite:///C:/data/expense_sharing.db`.

### Server

```powershell
uvicorn app.main:app --reload
```

- Welcome: http://127.0.0.1:8000/
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

### Tests

With the virtual environment activated:

```powershell
python -m pytest
```

### Docker

```powershell
docker build -t expense-sharing .
docker run -p 8000:8000 -v expense-data:/data expense-sharing
```

The image sets `DATABASE_URL` to `sqlite:////data/expense_sharing.db`. The named volume `expense-data` keeps that file between runs.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Welcome message, with links to `/docs` and `/health` |
| GET | `/health` | Health status (`{"status": "ok"}`) |
| POST | `/users` | Create user |
| GET | `/users` | List users |
| POST | `/groups` | Create group |
| POST | `/groups/{group_id}/members` | Add a user to a group (`{"user_id": 2}`) |
| GET | `/groups/{group_id}/members` | List members |
| POST | `/expenses` | Add an expense, split equally among current members |
| GET | `/groups/{group_id}/expenses` | Expense history |
| GET | `/groups/{group_id}/balances` | Who owes whom (`?simplify=true` for fewest payments) |
| POST | `/groups/{group_id}/settlements` | Record that one member paid another |
| GET | `/groups/{group_id}/settlements/suggested` | Fewest-payments plan to clear the group |

Errors: `404` unknown group/user, `400` rule violations (payer not in group, empty group, settling with yourself),
`409` duplicates, `422` invalid input (amount <= 0, blank names, more than 2 decimal places).

Example, the dinner from the assignment:

```
POST /expenses
{"group_id": 1, "paid_by": 1, "amount": 1200, "description": "Dinner"}

GET /groups/1/balances
{"Rahul": {"owes": {"Mohit": 400.0}}, "Ankit": {"owes": {"Mohit": 400.0}}}

POST /groups/1/settlements
{"from_user": 2, "to_user": 1, "amount": 400}       # Rahul pays Mohit
```

Differences from the suggested API:

- Balances are per group (`/groups/{id}/balances`), because a global `/balances` is ambiguous when users are in several groups.
- Adding a member takes only `user_id` in the body, since the group is already in the URL.

## Architecture

```
app/
  main.py      HTTP endpoints and database access
  services.py  pure business logic (splitting, netting, suggestions), no DB or HTTP
  models.py    SQLAlchemy tables
  schemas.py   request/response validation (Pydantic)
  database.py  engine and session
tests/         pytest: pure-logic tests and API tests (fresh in-memory DB per test)
```

Keeping the maths in `services.py` means it can be tested without a database or web server.

## Database design

```
users ──< group_members >── groups
  │                           │
  ├──< expenses >─────────────┤
  │       │                   │
  │       └──< expense_splits │
  └──< settlements >──────────┘
```

| Table | Columns |
|---|---|
| users | id, name (unique) |
| groups | id, name |
| group_members | id, group_id, user_id, unique(group_id, user_id) |
| expenses | id, group_id, paid_by, amount_paise, description, created_at |
| expense_splits | id, expense_id, user_id, amount_paise, unique(expense_id, user_id) |
| settlements | id, group_id, from_user, to_user, amount_paise, created_at |

Key choices:

- **Money is stored as integer paise**, never floats. The API takes and returns rupees.
  Amounts are limited to 2 decimal places.
- **`expense_splits` stores who owes what at the time of the expense.** If someone joins the group later,
  old expenses are unchanged. It is also what lets unequal splits be added without a schema change.
  The payer's own share is stored too, so the splits of an expense always add up to its amount.
- **Balances are not stored.** They are calculated from expenses and settlements on every request,
  so they cannot get out of sync. The cost is a query that grows with the number of expenses, fine at this scale.
- **Constraints are enforced in the database** as well as the API: foreign keys (switched on for SQLite),
  `amount_paise > 0`, unique membership.

## How the logic works

**Equal split.** `total // n` for everyone; the leftover paise (`total % n`) go one each to the lowest user ids,
so shares always sum exactly. Rs 100 among 3 gives 33.34, 33.33, 33.33.

**Balances.** Every split row means "this person owes the payer that amount" (the payer's own row is ignored,
so nobody owes themselves). A settlement is counted as the opposite debt. Debts between the same two people
are netted: A owes B 400 and B owes A 100 becomes A owes B 300.

## Enhancement: smart settlement suggestions

**Why.** The assignment's own opening question is "who should pay whom". Pairwise balances answer
"who owes whom" but not "what is the least annoying way to settle up".

**Problem it solves.** With several payers, pairwise balances can mean many small payments. Example: after two
expenses there are 3 pairwise debts, but one payment of Rs 300 clears everyone.

**How.** Work out each person's net position (total paid minus total owed; all positions sum to zero).
Then repeatedly make the person who owes the most pay the person who is owed the most. Each payment fully
clears at least one person, so n people need at most n-1 payments.

**Design decisions.**
- Runs on the same ledger as balances (expenses and settlements), so recorded settlements shrink the plan.
- Ties are broken by user id, so the output is deterministic and testable.
- `GET /balances?simplify=true` returns the same plan in the balances shape. This exists because paying
  someone who isn't directly owed (as the plan suggests) leaves a debt cycle in the pairwise view
  (A->B->C->A) even though everyone is actually settled. The simplified view stays clean.

**Tradeoffs.**
- Greedy is not always the true minimum number of payments (that problem is NP-hard). It is simple, fast and close.
- The plan may ask someone to pay a person they never directly owed money to. That is the point of the feature, but it
  is a different mental model from pairwise debts, which is why the pairwise view stays the default.

## Assumptions

- Expenses are split equally among **all current members** of the group at the time of the expense.
- The payer must be a member of the group. A group needs at least one member to have expenses.
- User names are unique (balances are keyed by name, as in the example response).
- Amounts are in rupees with at most 2 decimal places.
- No authentication: anyone can call any endpoint.
- Settlements are not checked against what is owed. Paying more than owed simply flips the debt.
  This is deliberate: suggested payments often go to someone who is not directly owed.
- Timestamps are stored in UTC (SQLite drops the timezone marker in responses).

## Improvements with more time

- Unequal and percentage splits (`expense_splits` already supports it; needs request validation that shares sum to the amount).
- Authentication, and restricting actions to group members.
- Pagination on expense history; list/delete/edit for expenses and settlements.
- Migrations (Alembic) instead of `create_all`.
- PostgreSQL for concurrent writes; SQLite is used here for zero-setup.
- Multiple currencies.
- A warning when a settlement exceeds what is owed.
