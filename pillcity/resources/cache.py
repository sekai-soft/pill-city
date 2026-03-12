import os

import redis

r = redis.Redis.from_url(os.environ["REDIS_URL"])
