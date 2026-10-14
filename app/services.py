"""Pure business logic (no database, no HTTP) so it is easy to unit test."""
from collections import defaultdict
from decimal import Decimal


def rupees_to_paise(amount: Decimal) -> int:
    return int(amount * 100)


def paise_to_rupees(paise: int) -> float:
    return paise / 100


def split_equally(total_paise: int, user_ids: list[int]) -> dict[int, int]:
    """Split total_paise among users. If it doesn't divide evenly, the leftover
    paise go one each to the lowest user ids, so the parts always add up exactly."""
    if not user_ids:
        raise ValueError("Cannot split among zero users")
    base, remainder = divmod(total_paise, len(user_ids))
    return {
        user_id: base + (1 if index < remainder else 0)
        for index, user_id in enumerate(sorted(user_ids))
    }


def net_pairwise_debts(debts: list[tuple[int, int, int]]) -> dict[tuple[int, int], int]:
    """Collapse (debtor, creditor, paise) entries into one net debt per pair.

    A owes B 400 and B owes A 100  ->  {(A, B): 300}. Pairs that cancel out are dropped.
    Returns {(debtor, creditor): paise} with only positive amounts.
    """
    # Store each pair once as (low_id, high_id); positive means low_id owes high_id.
    net: dict[tuple[int, int], int] = defaultdict(int)
    for debtor, creditor, paise in debts:
        if debtor == creditor:
            continue  # nobody owes themselves
        if debtor < creditor:
            net[(debtor, creditor)] += paise
        else:
            net[(creditor, debtor)] -= paise

    result = {}
    for (low, high), paise in net.items():
        if paise > 0:
            result[(low, high)] = paise
        elif paise < 0:
            result[(high, low)] = -paise
    return result


def net_positions(debts: list[tuple[int, int, int]]) -> dict[int, int]:
    """Each person's overall position from (debtor, creditor, paise) entries.
    Positive = is owed money, negative = owes money. All positions sum to zero."""
    positions: dict[int, int] = defaultdict(int)
    for debtor, creditor, paise in debts:
        if debtor == creditor:
            continue
        positions[creditor] += paise
        positions[debtor] -= paise
    return {user_id: paise for user_id, paise in positions.items() if paise != 0}


def suggest_settlements(positions: dict[int, int]) -> list[tuple[int, int, int]]:
    """Greedy plan that clears everyone's position with few payments.

    Repeatedly make the person who owes the most pay the person owed the most.
    Each payment fully clears at least one person, so n people need at most n-1 payments.
    Returns [(payer, receiver, paise)]. Greedy is not always the true minimum
    (that problem is NP-hard) but it is simple and close.
    """
    owed = {u: p for u, p in positions.items() if p > 0}
    owing = {u: -p for u, p in positions.items() if p < 0}
    payments = []
    while owed and owing:
        # Largest first; lowest id breaks ties so results are deterministic.
        receiver = max(owed, key=lambda u: (owed[u], -u))
        payer = max(owing, key=lambda u: (owing[u], -u))
        paise = min(owed[receiver], owing[payer])
        payments.append((payer, receiver, paise))
        owed[receiver] -= paise
        owing[payer] -= paise
        if owed[receiver] == 0:
            del owed[receiver]
        if owing[payer] == 0:
            del owing[payer]
    return payments
