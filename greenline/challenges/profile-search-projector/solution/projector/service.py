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
        connection.execute("BEGIN IMMEDIATE")
        try:
            checkpoint = connection.execute(
                "SELECT checkpoint FROM projector_state"
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT change_id, visible FROM changes WHERE change_id > ? ORDER BY change_id",
                (checkpoint,),
            ).fetchall()
            safe = checkpoint
            for change_id, visible in rows:
                if change_id != safe + 1 or not visible:
                    break
                safe = change_id
            changes = connection.execute(
                """SELECT change_id, profile_id, operation, display_name
                   FROM changes WHERE change_id > ? AND change_id <= ?
                   ORDER BY change_id LIMIT ?""",
                (checkpoint, safe, self.batch_size),
            ).fetchall()
            if not changes:
                connection.rollback()
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
            if crash_before_checkpoint:
                raise SimulatedCrash("crashed before commit")
            connection.execute("UPDATE projector_state SET checkpoint = ?", (changes[-1][0],))
            connection.commit()
            return len(changes)
        except Exception:
            connection.rollback()
            raise
