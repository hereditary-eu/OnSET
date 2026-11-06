import os
from typing import Callable, Generic, TypeVar

import redis
from pydantic import BaseModel
from redis_om import Migrator

T = TypeVar("T", bound=BaseModel)


class RedisCache(Generic[T]):
    """JSON cache of pydantic models in Redis, entries expire after ``ttl`` seconds."""

    def __init__(
        self, redis_url: str = "redis://localhost:6379/0", model: type[T] = BaseModel
    ):
        os.environ["REDIS_OM_URL"] = redis_url
        self.model = model
        # timeouts: an unreachable Redis must not block request threads forever
        self.redis = redis.Redis.from_url(
            redis_url, socket_timeout=20, socket_connect_timeout=5
        )
        Migrator().run()

    def get(self, key: str) -> T | None:
        data = self.redis.get(key)
        if data:
            return self.model.model_validate_json(data)
        return None

    def set(self, key: str, value: T, ttl=24 * 60 * 60):
        self.redis.setex(key, ttl, value.model_dump_json())

    def get_or_set(self, key: str, compute: Callable[[], T]) -> T:
        """The cached value of ``key``, computing and caching it on a miss."""
        value = self.get(key)
        if value is None:
            value = compute()
            self.set(key, value)
        return value

    def __setitem__(self, key: str, value: T) -> None:
        return self.set(key, value)

    def __getitem__(self, key: str) -> T | None:
        return self.get(key)
