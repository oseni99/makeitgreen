import threading
from collections.abc import Callable

import pytest

from orders.inventory import InsufficientStock, Inventory
from orders.service import Order, OrderService


def make_service(
    stock: int = 10,
    *,
    authorize: Callable[[str], None] | None = None,
    before_checkout: Callable[[Order], None] | None = None,
) -> OrderService:
    inventory = Inventory(authorize=authorize)
    if stock:
        inventory.add_stock("GPU-4090", stock)
    return OrderService(inventory, before_checkout=before_checkout)


def run_concurrently(actions: list[Callable[[], bool]]) -> tuple[list[bool], list[BaseException]]:
    start = threading.Barrier(len(actions))
    results: list[bool] = []
    errors: list[BaseException] = []

    def worker(action: Callable[[], bool]) -> None:
        try:
            start.wait(timeout=2)
            results.append(action())
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    return results, errors


def test_creates_and_registers_order() -> None:
    service = make_service()
    order = service.create_order("GPU-4090", qty=2, unit_price_cents=1_999)

    assert order.sku == "GPU-4090"
    assert order.qty == 2
    assert order.subtotal_cents == 3_998
    assert order.total_cents == 3_998
    assert order.status == "created"
    assert service.orders[order.id] is order


def test_rejects_non_positive_order_quantity() -> None:
    service = make_service()

    with pytest.raises(ValueError, match="qty must be positive"):
        service.create_order("GPU-4090", qty=0, unit_price_cents=100)

    assert service.orders == {}


def test_rejects_blank_sku() -> None:
    service = make_service()

    with pytest.raises(ValueError, match="sku must not be blank"):
        service.create_order("  ", qty=1, unit_price_cents=100)

    assert service.orders == {}


@pytest.mark.parametrize("unit_price_cents", [0, -1])
def test_rejects_non_positive_unit_price(unit_price_cents: int) -> None:
    service = make_service()

    with pytest.raises(ValueError, match="unit price must be positive"):
        service.create_order("GPU-4090", qty=1, unit_price_cents=unit_price_cents)

    assert service.orders == {}


def test_applies_discount_boundaries_without_compounding() -> None:
    service = make_service()
    below = service.create_order("GPU-4090", qty=1, unit_price_cents=4_999)
    five_percent = service.create_order("GPU-4090", qty=5, unit_price_cents=1_000)
    ten_percent = service.create_order("GPU-4090", qty=5, unit_price_cents=2_000)

    service.apply_discount(below)
    service.apply_discount(five_percent)
    service.apply_discount(ten_percent)
    service.apply_discount(ten_percent)

    assert (below.discount_cents, below.total_cents) == (0, 4_999)
    assert (five_percent.discount_cents, five_percent.total_cents) == (250, 4_750)
    assert (ten_percent.discount_cents, ten_percent.total_cents) == (1_000, 9_000)


def test_insufficient_reservation_leaves_stock_unchanged() -> None:
    inventory = Inventory()
    inventory.add_stock("GPU", 2)

    with pytest.raises(InsufficientStock):
        inventory.reserve("GPU", 3)

    assert inventory.available("GPU") == 2


def test_rejects_non_positive_reservation_quantity() -> None:
    inventory = Inventory()
    inventory.add_stock("GPU", 2)

    with pytest.raises(ValueError, match="qty must be positive"):
        inventory.reserve("GPU", 0)

    assert inventory.available("GPU") == 2


def test_different_skus_reach_authorization_concurrently() -> None:
    authorization_barrier = threading.Barrier(2)

    def authorize(_sku: str) -> None:
        authorization_barrier.wait(timeout=2)

    inventory = Inventory(authorize=authorize)
    inventory.add_stock("GPU", 1)
    inventory.add_stock("CPU", 1)

    results, errors = run_concurrently(
        [
            lambda: (inventory.reserve("GPU", 1) is None),
            lambda: (inventory.reserve("CPU", 1) is None),
        ]
    )

    assert errors == []
    assert results == [True, True]
    assert inventory.available("GPU") == 0
    assert inventory.available("CPU") == 0


@pytest.mark.parametrize(
    ("stock", "quantity", "buyers"),
    [(1, 1, 4), (4, 2, 4), (10, 4, 4)],
    ids=["last-unit", "pairs", "remainder"],
)
def test_concurrent_reservations_never_oversell(
    stock: int,
    quantity: int,
    buyers: int,
) -> None:
    authorization_barrier = threading.Barrier(buyers)
    inventory = Inventory(authorize=lambda _sku: authorization_barrier.wait(timeout=2))
    inventory.add_stock("GPU", stock)

    def reserve() -> bool:
        try:
            inventory.reserve("GPU", quantity)
        except InsufficientStock:
            return False
        return True

    results, errors = run_concurrently([reserve for _ in range(buyers)])
    expected_successes = min(buyers, stock // quantity)

    assert errors == []
    assert sum(results) == expected_successes
    assert inventory.available("GPU") == stock - expected_successes * quantity


def test_retrying_completed_checkout_does_not_reserve_twice() -> None:
    service = make_service(stock=2)
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)

    assert service.checkout(order) is True
    assert service.checkout(order) is True

    assert order.status == "completed"
    assert service.inventory.available("GPU-4090") == 1


def test_rejected_checkout_remains_terminal_after_restock() -> None:
    service = make_service(stock=0)
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)

    assert service.checkout(order) is False
    service.inventory.add_stock("GPU-4090", 1)
    assert service.checkout(order) is False

    assert order.status == "rejected"
    assert service.inventory.available("GPU-4090") == 1


def test_authorization_error_restores_created_state_without_consuming_stock() -> None:
    authorization_error = RuntimeError("payment network unavailable")
    service = make_service(
        stock=1,
        authorize=lambda _sku: (_ for _ in ()).throw(authorization_error),
    )
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)

    with pytest.raises(RuntimeError, match="payment network unavailable"):
        service.checkout(order)

    assert order.status == "created"
    assert service.inventory.available("GPU-4090") == 1


def test_concurrent_retries_of_one_order_reserve_once() -> None:
    checkout_barrier = threading.Barrier(2)
    service = make_service(
        stock=2,
        before_checkout=lambda _order: checkout_barrier.wait(timeout=2),
    )
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)

    results, errors = run_concurrently(
        [lambda: service.checkout(order), lambda: service.checkout(order)]
    )

    assert errors == []
    assert results == [True, True]
    assert order.status == "completed"
    assert service.inventory.available("GPU-4090") == 1


def test_cancelling_completed_order_restocks_inventory() -> None:
    service = make_service(stock=1)
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)
    assert service.checkout(order) is True

    assert service.cancel(order) is True

    assert order.status == "cancelled"
    assert service.inventory.available("GPU-4090") == 1


def test_cannot_cancel_an_order_that_never_completed() -> None:
    service = make_service(stock=1)
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)

    assert service.cancel(order) is False

    assert order.status == "created"
    assert service.inventory.available("GPU-4090") == 1


def test_repeated_cancellation_does_not_restock_twice() -> None:
    service = make_service(stock=1)
    order = service.create_order("GPU-4090", qty=1, unit_price_cents=100)
    assert service.checkout(order) is True

    assert service.cancel(order) is True
    assert service.cancel(order) is False

    assert order.status == "cancelled"
    assert service.inventory.available("GPU-4090") == 1
