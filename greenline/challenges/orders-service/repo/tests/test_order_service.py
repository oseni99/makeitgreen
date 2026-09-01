import threading

from orders.inventory import Inventory
from orders.service import OrderService


def make_service(stock: int = 10) -> OrderService:
    inv = Inventory()
    inv.add_stock("GPU-4090", stock)
    return OrderService(inv)


def test_creates_order() -> None:
    svc = make_service()
    order = svc.create_order("GPU-4090", qty=2, unit_price_cents=1999)
    assert order.sku == "GPU-4090"
    assert order.subtotal_cents == 3998
    assert order.status == "created"
    assert svc.orders[order.id] is order


def test_applies_discount() -> None:
    svc = make_service()
    order = svc.create_order("GPU-4090", qty=3, unit_price_cents=2_000)
    svc.apply_discount(order)
    assert order.discount_cents == 300  # 5% tier
    assert order.total_cents == 5_700

    big = svc.create_order("GPU-4090", qty=6, unit_price_cents=2_000)
    svc.apply_discount(big)
    assert big.discount_cents == 1_200  # 10% tier


def test_processes_concurrent_checkouts() -> None:
    """50 buyers race for 10 units. Exactly 10 should win; stock must end at 0."""
    svc = make_service(stock=10)
    orders = [svc.create_order("GPU-4090", qty=1, unit_price_cents=99_900)
              for _ in range(50)]

    results = []
    barrier = threading.Barrier(len(orders))

    def buy(order):
        barrier.wait()
        results.append(svc.checkout(order))

    threads = [threading.Thread(target=buy, args=(o,)) for o in orders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    remaining = svc.inventory.available("GPU-4090")
    assert remaining == 0, f"expected inventory: 0, actual inventory: {remaining}"
    assert sum(results) == 10, f"expected 10 successful checkouts, got {sum(results)}"
