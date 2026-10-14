import pytest

from app.services import net_pairwise_debts, split_equally


def test_split_equally_even():
    assert split_equally(120000, [1, 2, 3]) == {1: 40000, 2: 40000, 3: 40000}


def test_split_equally_remainder_goes_to_lowest_ids_and_sums_exactly():
    # Rs 100.00 / 3 -> 33.34, 33.33, 33.33
    shares = split_equally(10000, [3, 1, 2])
    assert shares == {1: 3334, 2: 3333, 3: 3333}
    assert sum(shares.values()) == 10000


def test_split_equally_needs_users():
    with pytest.raises(ValueError):
        split_equally(100, [])


def test_net_ignores_self_debt():
    assert net_pairwise_debts([(1, 1, 400)]) == {}


def test_net_combines_same_direction():
    assert net_pairwise_debts([(2, 1, 400), (2, 1, 100)]) == {(2, 1): 500}


def test_net_offsets_opposite_directions():
    assert net_pairwise_debts([(2, 1, 400), (1, 2, 100)]) == {(2, 1): 300}
    assert net_pairwise_debts([(1, 2, 400), (2, 1, 100)]) == {(1, 2): 300}


def test_net_drops_pairs_that_cancel():
    assert net_pairwise_debts([(1, 2, 250), (2, 1, 250)]) == {}


from app.services import net_positions, suggest_settlements  # noqa: E402


def test_net_positions_sum_to_zero():
    positions = net_positions([(2, 1, 400), (3, 1, 400), (1, 2, 100)])
    assert positions == {1: 700, 2: -300, 3: -400}
    assert sum(positions.values()) == 0


def test_suggest_settlements_simple():
    assert suggest_settlements({1: 800, 2: -400, 3: -400}) == [(2, 1, 400), (3, 1, 400)]


def test_suggest_settlements_uses_fewer_payments_than_pairwise():
    # 4 people, 2 owe and 2 are owed: needs at most 3 payments.
    positions = {1: 500, 2: 300, 3: -600, 4: -200}
    payments = suggest_settlements(positions)
    assert len(payments) <= len(positions) - 1
    # Applying the payments must clear everyone to exactly zero.
    result = dict(positions)
    for payer, receiver, paise in payments:
        result[payer] += paise
        result[receiver] -= paise
    assert all(v == 0 for v in result.values())


def test_suggest_settlements_nothing_to_do():
    assert suggest_settlements({}) == []
