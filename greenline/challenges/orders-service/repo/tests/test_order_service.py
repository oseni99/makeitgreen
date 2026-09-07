import threading
from collections.abc import Callable

import pytest

from orders.inventory import InsufficientStock, Inventory
from orders.service import OrderService


def make_service(stock: int = 10) -> OrderService:
    inventory = Inventory()
    inventory.add_stock("GPU-4090", stock)
    return OrderService(inventory)


def run_concurrently(count: int, action: Callable[[], bool]) -> tuple[list[bool], list[BaseException]]:
    start = threading.Barrier(count)
    results: list[bool] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            start.wait()
            results.append(action())
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(count)]
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


@pytest.mark.parametrize("quantity", [0, -1])
def test_rejects_non_positive_order_quantity(quantity: int) -> None:
    service = make_service()

    with pytest.raises(ValueError, match="qty must be positive"):
        service.create_order("GPU-4090", qty=quantity, unit_price_cents=100)

    assert service.orders == {}


def test_applies_discount_boundaries() -> None:
    service = make_service()
    below = service.create_order("GPU-4090", qty=1, unit_price_cents=4_999)
    five_percent = service.create_order("GPU-4090", qty=5, unit_price_cents=1_000)
    ten_percent = service.create_order("GPU-4090", qty=5, unit_price_cents=2_000)

    service.apply_discount(below)
    service.apply_discount(five_percent)
    service.apply_discount(ten_percent)

    assert (below.discount_cents, below.total_cents) == (0, 4_999)
    assert (five_percent.discount_cents, five_percent.total_cents) == (250, 4_750)
    assert (ten_percent.discount_cents, ten_percent.total_cents) == (1_000, 9_000)


def test_different_skus_reach_authorization_concurrently() -> None:
    authorizing = set()
    authorizing_lock = threading.Lock()
    both_authorizing = threading.Event()
    release_authorization = threading.Event()

    def authorize(sku: str) -> None:
        with authorizing_lock:
            authorizing.add(sku)
            if authorizing == {"GPU", "CPU"}:
                both_authorizing.set()
        if not release_authorization.wait(timeout=2):
            raise TimeoutError(f"authorization for {sku} was not released")

    inventory = Inventory(authorize=authorize)
    inventory.add_stock("GPU", 1)
    inventory.add_stock("CPU", 1)
    errors: list[BaseException] = []

    def reserve(sku: str) -> None:
        try:
            inventory.reserve(sku, 1)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=reserve, args=("GPU",)),
        threading.Thread(target=reserve, args=("CPU",)),
    ]
    for thread in threads:
        thread.start()
    try:
        assert both_authorizing.wait(timeout=1), authorizing
    finally:
        release_authorization.set()
        for thread in threads:
            thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert inventory.available("GPU") == 0
    assert inventory.available("CPU") == 0


INVENTORY_RACES = [
    (1, 1, 8),
    (2, 1, 8),
    (5, 1, 12),
    (4, 2, 8),
    (6, 2, 8),
    (9, 3, 8),
    (10, 4, 8),
]


@pytest.mark.parametrize(
    ("stock", "quantity", "buyers"),
    INVENTORY_RACES,
    ids=["last-unit", "two-units", "five-units", "pairs", "three-pairs", "triples", "remainder"],
)
def test_concurrent_inventory_reservations_are_atomic(
    stock: int,
    quantity: int,
    buyers: int,
) -> None:
    inventory = Inventory()
    inventory.add_stock("GPU", stock)

    def reserve() -> bool:
        try:
            inventory.reserve("GPU", quantity)
        except InsufficientStock:
            return False
        return True

    results, errors = run_concurrently(buyers, reserve)
    expected_successes = min(buyers, stock // quantity)

    assert errors == []
    assert sum(results) == expected_successes
    assert inventory.available("GPU") == stock - expected_successes * quantity
    assert inventory.available("GPU") >= 0


CHECKOUT_RACES = [
    (1, 1, 8),
    (3, 1, 10),
    (4, 2, 8),
    (6, 2, 8),
    (8, 3, 8),
    (10, 4, 8),
]


@pytest.mark.parametrize(
    ("stock", "quantity", "buyers"),
    CHECKOUT_RACES,
    ids=["single-winner", "three-winners", "two-pairs", "three-pairs", "triple-remainder", "quad-remainder"],
)
def test_concurrent_checkouts_complete_only_funded_orders(
    stock: int,
    quantity: int,
    buyers: int,
) -> None:
    service = make_service(stock)
    orders = [
        service.create_order("GPU-4090", qty=quantity, unit_price_cents=100)
        for _ in range(buyers)
    ]
    order_index = iter(orders)

    def checkout() -> bool:
        return service.checkout(next(order_index))

    results, errors = run_concurrently(buyers, checkout)
    expected_successes = min(buyers, stock // quantity)

    assert errors == []
    assert sum(results) == expected_successes
    assert sum(order.status == "completed" for order in orders) == expected_successes
    assert sum(order.status == "rejected" for order in orders) == buyers - expected_successes
    assert service.inventory.available("GPU-4090") == stock - expected_successes * quantity
