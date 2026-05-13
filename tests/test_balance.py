# Pure unit tests for the two algorithm functions.
# No DB, no HTTP - just Decimal arithmetic.

import uuid
from decimal import Decimal

from app.services.balance_service import _calculate_net_balances, _simplify_debts


def make_uid() -> uuid.UUID:
    return uuid.uuid4()


# --- _simplify_debts -------------------------------------------------------------

class TestSimplifyDebts:

    def test_simple_two_person(self):
        """A owes B 50."""
        a, b = make_uid(), make_uid()
        net = {a: Decimal("50.00"), b: Decimal("-50.00")}
        debts = _simplify_debts(net)
        assert len(debts) == 1
        assert debts[0] == (b, a, Decimal("50.00"))

    def test_three_person_single_creditor(self):
        """B and C each owe A 100."""
        a, b, c = make_uid(), make_uid(), make_uid()
        net = {
            a: Decimal("200.00"),
            b: Decimal("-100.00"),
            c: Decimal("-100.00"),
        }
        debts = _simplify_debts(net)
        assert len(debts) == 2
        total_paid = sum(d[2] for d in debts)
        assert total_paid == Decimal("200.00")
        # Both B and C must pay A
        receivers = {d[1] for d in debts}
        assert receivers == {a}

    def test_three_person_simplification(self):
        """
        A=+100, B=+50, C=-80, D=-70
        Greedy should produce fewer transactions than naive N*(N-1)/2.
        """
        a, b, c, d = make_uid(), make_uid(), make_uid(), make_uid()
        net = {
            a: Decimal("100.00"),
            b: Decimal("50.00"),
            c: Decimal("-80.00"),
            d: Decimal("-70.00"),
        }
        debts = _simplify_debts(net)
        # Greedy produces at most n-1 = 3 transactions
        assert len(debts) <= 3
        # Sum of all payments equals total debt
        total_settled = sum(debt[2] for debt in debts)
        assert total_settled == Decimal("150.00")

    def test_already_settled(self):
        """All net balances are zero - no transactions needed."""
        a, b = make_uid(), make_uid()
        net = {a: Decimal("0.00"), b: Decimal("0.00")}
        debts = _simplify_debts(net)
        assert debts == []

    def test_below_threshold_treated_as_zero(self):
        """Balances smaller than 0.005 (half a cent) are ignored."""
        a, b = make_uid(), make_uid()
        net = {a: Decimal("0.001"), b: Decimal("-0.001")}
        debts = _simplify_debts(net)
        assert debts == []

    def test_single_member(self):
        """One person - nothing to simplify."""
        a = make_uid()
        net = {a: Decimal("0.00")}
        debts = _simplify_debts(net)
        assert debts == []

    def test_debt_amounts_are_positive(self):
        """All returned amounts must be > 0."""
        a, b, c = make_uid(), make_uid(), make_uid()
        net = {a: Decimal("300"), b: Decimal("-100"), c: Decimal("-200")}
        debts = _simplify_debts(net)
        assert all(d[2] > 0 for d in debts)


# --- _calculate_net_balances ------------------------------------------------------

class MockExpense:
    """Minimal mock — only payers and splits needed."""
    def __init__(self, payers, splits):
        self.payers = payers
        self.splits = splits

class MockPayer:
    def __init__(self, user_id, amount):
        self.user_id = user_id
        self.amount = Decimal(str(amount))

class MockSplit:
    def __init__(self, user_id, amount):
        self.user_id = user_id
        self.amount = Decimal(str(amount))

class MockSettlement:
    def __init__(self, payer_id, receiver_id, amount):
        self.payer_id = payer_id
        self.receiver_id = receiver_id
        self.amount = Decimal(str(amount))


class TestCalculateNetBalances:

    def test_simple_equal_split(self):
        """Alice pays 100, split equally between alice and bob."""
        alice, bob = make_uid(), make_uid()
        expenses = [MockExpense(
            payers=[MockPayer(alice, 100)],
            splits=[MockSplit(alice, 50), MockSplit(bob, 50)],
        )]
        net = _calculate_net_balances(expenses, [], {alice, bob})
        assert net[alice] == Decimal("50")   # paid 100, owes 50 → net +50
        assert net[bob] == Decimal("-50")    # paid 0, owes 50 → net -50

    def test_settlement_reduces_debt(self):
        """After bob pays alice 50, both net balances become 0."""
        alice, bob = make_uid(), make_uid()
        expenses = [MockExpense(
            payers=[MockPayer(alice, 100)],
            splits=[MockSplit(alice, 50), MockSplit(bob, 50)],
        )]
        settlements = [MockSettlement(payer_id=bob, receiver_id=alice, amount=50)]
        net = _calculate_net_balances(expenses, settlements, {alice, bob})
        assert net[alice] == Decimal("0")
        assert net[bob] == Decimal("0")

    def test_member_with_no_expenses_has_zero(self):
        """A member who is in no expenses should still appear with net=0."""
        alice, bob, charlie = make_uid(), make_uid(), make_uid()
        expenses = [MockExpense(
            payers=[MockPayer(alice, 100)],
            splits=[MockSplit(alice, 50), MockSplit(bob, 50)],
        )]
        # Charlie has no expenses — still initialized to 0
        net = _calculate_net_balances(expenses, [], {alice, bob, charlie})
        assert net[charlie] == Decimal("0")

    def test_multiple_payers(self):
        """Alice and Bob each pay part of a shared expense."""
        alice, bob = make_uid(), make_uid()
        expenses = [MockExpense(
            payers=[MockPayer(alice, 70), MockPayer(bob, 30)],
            splits=[MockSplit(alice, 50), MockSplit(bob, 50)],
        )]
        net = _calculate_net_balances(expenses, [], {alice, bob})
        assert net[alice] == Decimal("20")   # 70 paid - 50 owed
        assert net[bob] == Decimal("-20")    # 30 paid - 50 owed

    def test_sum_of_net_balances_is_zero(self):
        """
        Conservation law: sum of all net balances must always equal zero.
        Money is not created or destroyed.
        """
        alice, bob, charlie = make_uid(), make_uid(), make_uid()
        expenses = [
            MockExpense(
                payers=[MockPayer(alice, 300)],
                splits=[MockSplit(alice, 100), MockSplit(bob, 100), MockSplit(charlie, 100)],
            ),
            MockExpense(
                payers=[MockPayer(bob, 60)],
                splits=[MockSplit(alice, 20), MockSplit(bob, 20), MockSplit(charlie, 20)],
            ),
        ]
        settlements = [MockSettlement(bob, alice, 60)]
        net = _calculate_net_balances(expenses, settlements, {alice, bob, charlie})
        assert sum(net.values()) == Decimal("0")