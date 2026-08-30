from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    customer_id: str
    status: str


class OrderRepository:
    def find_for_customer(
        self, connection: sqlite3.Connection, customer_id: str
    ) -> tuple[Order, ...]:
        rows = connection.execute(
            "SELECT id, customer_id, status FROM orders WHERE customer_id = ? ORDER BY id",
            (customer_id,),
        ).fetchall()
        return tuple(Order(int(row[0]), str(row[1]), str(row[2])) for row in rows)
