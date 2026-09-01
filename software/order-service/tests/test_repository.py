from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from order_service.repository import OrderRepository


class OrderRepositoryTest(unittest.TestCase):
    def test_customer_id_is_bound_as_a_parameter(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id TEXT, status TEXT)"
        )
        connection.executemany(
            "INSERT INTO orders (customer_id, status) VALUES (?, ?)",
            [("customer_123", "ready"), ("customer_456", "queued")],
        )

        orders = OrderRepository().find_for_customer(connection, "customer_123")

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].customer_id, "customer_123")

    def test_status_filter_is_bound_with_customer_id(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id TEXT, status TEXT)"
        )
        connection.executemany(
            "INSERT INTO orders (customer_id, status) VALUES (?, ?)",
            [
                ("customer_123", "ready"),
                ("customer_123", "queued"),
                ("customer_456", "ready"),
            ],
        )

        orders = OrderRepository().find_for_customer(
            connection,
            "customer_123",
            status="ready",
        )

        self.assertEqual(
            [(order.customer_id, order.status) for order in orders], [("customer_123", "ready")]
        )


if __name__ == "__main__":
    unittest.main()
