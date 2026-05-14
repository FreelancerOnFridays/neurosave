from __future__ import annotations

from taskiq_redis import ListQueueBroker, RedisScheduleSource

from config import settings

broker = ListQueueBroker(settings.redis_url)
schedule_source = RedisScheduleSource(settings.redis_url)
