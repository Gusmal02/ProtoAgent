"""Real SQLite read adapter. Typed operation, parameter binding and entity scope."""
import json
import sqlite3
from .contracts import QuerySpec, Evidence, digest

class SQLiteConnector:
    name = "sqlite"

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def query(self, spec: QuerySpec) -> tuple[Evidence, ...]:
        if spec.connector != self.name or spec.operation != "overdue_invoices":
            raise ValueError("unsupported typed query")
        if spec.parameters:
            raise ValueError("parameters not supported by this operation")
        rows = self.connection.execute(
            "SELECT invoice_id, amount FROM invoices WHERE entity_id = ? AND overdue = 1 ORDER BY invoice_id",
            (spec.entity,)).fetchall()
        return tuple(Evidence(digest([self.name, spec.entity, row]), self.name, spec.entity, "fixture-v1",
                              json.dumps({"invoice_id": row[0], "amount": row[1]}, sort_keys=True),
                              "verified_finite") for row in rows)

