from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread

import pytest

from handoff import ClosedQueue, HandoffQueue


def test_fifo_and_close_drains_accepted_items() -> None:
    queue = HandoffQueue[str]()
    queue.put("one")
    queue.put("two")
    queue.close()

    assert [queue.get(), queue.get(), queue.get()] == ["one", "two", None]


def test_put_after_close_is_rejected() -> None:
    queue = HandoffQueue[str]()
    queue.close()
    with pytest.raises(ClosedQueue):
        queue.put("late")


def test_spurious_wakeup_does_not_end_consumer() -> None:
    woke = Event()
    queue = HandoffQueue[str](expected_waiters=1, on_wake=woke)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(queue.get)
        assert queue.all_waiting.wait(timeout=1)
        queue.poke_all()
        assert woke.wait(timeout=1)
        queue.put("thumbnail-1")
        assert result.result(timeout=1) == "thumbnail-1"


def test_close_wakes_every_parked_consumer() -> None:
    queue = HandoffQueue[str](expected_waiters=3)
    threads = [Thread(target=queue.get, daemon=True) for _ in range(3)]
    for thread in threads:
        thread.start()
    assert queue.all_waiting.wait(timeout=1)

    queue.close()
    for thread in threads:
        thread.join(timeout=0.2)
    still_alive = [thread for thread in threads if thread.is_alive()]
    queue.poke_all()  # cleanup if the implementation failed the broadcast contract
    for thread in still_alive:
        thread.join(timeout=1)

    assert still_alive == []


def test_concurrent_consumers_receive_each_item_once() -> None:
    queue = HandoffQueue[int]()
    for item in range(20):
        queue.put(item)
    queue.close()

    def drain() -> list[int]:
        found = []
        while (item := queue.get()) is not None:
            found.append(item)
        return found

    with ThreadPoolExecutor(max_workers=4) as pool:
        chunks = list(pool.map(lambda _: drain(), range(4)))
    flattened = [item for chunk in chunks for item in chunk]
    assert sorted(flattened) == list(range(20))
    assert len(flattened) == len(set(flattened))
