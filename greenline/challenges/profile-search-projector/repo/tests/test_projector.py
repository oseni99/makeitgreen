import pytest

from projector import Database, Projector, SimulatedCrash


def test_visible_changes_project_in_order_and_updates_are_idempotent() -> None:
    db = Database()
    db.change(1, "p1", "upsert", "Ada")
    db.change(2, "p1", "upsert", "Ada Lovelace")

    assert Projector(db).run_once() == 2
    assert db.projection() == {"p1": "Ada Lovelace"}
    assert Projector(db).run_once() == 0


def test_invisible_lower_id_blocks_checkpoint_advancement() -> None:
    db = Database()
    db.change(1, "p1", "upsert", "Ada", visible=False)
    db.change(2, "p2", "upsert", "Grace", visible=True)
    projector = Projector(db)

    assert projector.run_once() == 0
    assert db.checkpoint() == 0
    assert db.projection() == {}

    db.reveal(1)
    assert projector.run_once() == 2
    assert db.projection() == {"p1": "Ada", "p2": "Grace"}


def test_delete_tombstone_removes_projection() -> None:
    db = Database()
    db.change(1, "p1", "upsert", "Ada")
    db.change(2, "p1", "delete", None)
    assert Projector(db).run_once() == 2
    assert db.projection() == {}


def test_projection_and_checkpoint_roll_back_together_on_crash() -> None:
    db = Database()
    db.change(1, "p1", "upsert", "Ada")

    with pytest.raises(SimulatedCrash):
        Projector(db).run_once(crash_before_checkpoint=True)

    assert db.checkpoint() == 0
    assert db.projection() == {}
    assert Projector(db).run_once() == 1


def test_batch_size_bounds_progress() -> None:
    db = Database()
    for change_id in range(1, 6):
        db.change(change_id, f"p{change_id}", "upsert", f"Name {change_id}")
    projector = Projector(db, batch_size=2)

    assert projector.run_once() == 2
    assert db.checkpoint() == 2
    assert len(db.projection()) == 2


@pytest.mark.parametrize("hidden_id", [1, 2, 3, 4, 5])
def test_each_invisible_gap_blocks_all_later_visible_changes(hidden_id: int) -> None:
    db = Database()
    for change_id in range(1, 7):
        db.change(
            change_id,
            f"p{change_id}",
            "upsert",
            f"Name {change_id}",
            visible=change_id != hidden_id,
        )

    processed = Projector(db).run_once()

    assert processed == hidden_id - 1
    assert db.checkpoint() == hidden_id - 1
    assert set(db.projection()) == {
        f"p{change_id}" for change_id in range(1, hidden_id)
    }


@pytest.mark.parametrize("change_count", [1, 2, 5])
def test_crash_rolls_back_every_projected_change_and_checkpoint(
    change_count: int,
) -> None:
    db = Database()
    for change_id in range(1, change_count + 1):
        db.change(change_id, f"p{change_id}", "upsert", f"Name {change_id}")

    with pytest.raises(SimulatedCrash):
        Projector(db).run_once(crash_before_checkpoint=True)

    assert db.checkpoint() == 0
    assert db.projection() == {}


@pytest.mark.parametrize("batch_size", [1, 3])
def test_batch_stops_before_hidden_change_even_when_limit_extends_past_it(
    batch_size: int,
) -> None:
    db = Database()
    db.change(1, "p1", "upsert", "Ada", visible=False)
    for change_id in range(2, 5):
        db.change(change_id, f"p{change_id}", "upsert", f"Name {change_id}")

    assert Projector(db, batch_size=batch_size).run_once() == 0
    assert db.checkpoint() == 0
    assert db.projection() == {}
