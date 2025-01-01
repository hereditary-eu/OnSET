from redis_om import HashModel
import redis
from pydantic import BaseModel
from redis_om import Field, HashModel, Migrator
import os
from typing import TypeVar, Generic, List

T = TypeVar("T", bound=BaseModel)


class RedisCache(Generic[T]):
    def __init__(
        self, redis_url: str = "redis://localhost:6379/0", model: T = BaseModel
    ):
        os.environ["REDIS_OM_URL"] = redis_url
        self.model = model
        self.redis = redis.Redis.from_url(redis_url)
        Migrator().run()

    def get(self, key: str) -> T:
        data = self.redis.get(key)
        if data:
            parsed_data = self.model.model_validate_json(data)
            return parsed_data

    def set(self, key: str, value: T, ttl=10 * 60):
        self.redis.setex(key, ttl, value.model_dump_json())

    def __setitem__(self, key: str, value: T) -> None:
        return self.set(key, value)

    def __getitem__(self, key: str) -> T:
        return self.get(key)
