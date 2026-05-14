import redis
import json

r = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)

CACHE_TTL = 60 * 60 * 24 * 7


def get_cached_result(file_hash):

    cached = r.get(f"scan:{file_hash}")

    if not cached:
        return None

    return json.loads(cached)


def cache_result(file_hash, result):

    r.setex(
        f"scan:{file_hash}",
        CACHE_TTL,
        json.dumps(result)
    )