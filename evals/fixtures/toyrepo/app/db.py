"""Database connection handling and pooling."""

from app.config import POOL_SIZE


class Connection:
    def __init__(self, conn_id: int) -> None:
        self.conn_id = conn_id

    def query(self, sql: str) -> list[dict]:
        return []


class ConnectionPool:
    """Fixed-size pool of database connections.

    Bug surface: connections are never returned to the pool after use, so
    under sustained load the pool is exhausted and new requests block forever.
    """

    def __init__(self, size: int = POOL_SIZE) -> None:
        self._free = [Connection(i) for i in range(size)]

    def acquire(self) -> Connection:
        return self._free.pop()


_pool = ConnectionPool()


def get_connection() -> Connection:
    return _pool.acquire()
