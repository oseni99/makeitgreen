from __future__ import annotations

from .database import Database


class SimulatedCrash(RuntimeError):
    pass


class Projector:
    def __init__(self, database: Database, *, batch_size: int = 100) -> None:
        self.db = database
        self.batch_size = batch_size

    def run_once(self, *, crash_before_checkpoint: bool = False) -> int:
        connection = self.db.connection
        checkpoint = self.db.checkpoint()
        changes = connection.execute(
            """SELECT change_id, profile_id, operation, display_name
               FROM changes WHERE visible = 1 AND change_id > ?
               ORDER BY change_id LIMIT ?""",
            (checkpoint, self.batch_size),
        ).fetchall()
        if not changes:
            return 0

        for _, profile_id, operation, display_name in changes:
            if operation == "delete":
                connection.execute("DELETE FROM search_profiles WHERE profile_id = ?", (profile_id,))
            else:
                connection.execute(
                    """INSERT INTO search_profiles VALUES (?, ?)
                       ON CONFLICT(profile_id) DO UPDATE SET display_name = excluded.display_name""",
                    (profile_id, display_name),
                )
        # BUG: projection writes become durable before the checkpoint.
        connection.commit()
        if crash_before_checkpoint:
            raise SimulatedCrash("crashed after projection")
        connection.execute("UPDATE projector_state SET checkpoint = ?", (changes[-1][0],))
        connection.commit()
        return len(changes)
