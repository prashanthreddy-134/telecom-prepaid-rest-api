
import json

import pytest
import redis

import app.cache as cache


class FakeRedis:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.get_calls = []
        self.set_calls = []
        self.incr_calls = []

    def get(self, key):
        self.get_calls.append(key)

        if self.error:
            raise self.error

        return self.value

    def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))

        if self.error:
            raise self.error

        return True

    def incr(self, key):
        self.incr_calls.append(key)

        if self.error:
            raise self.error

        return 1


@pytest.fixture(autouse=True)
def reset_redis_client(monkeypatch):
    monkeypatch.setattr(cache, "_redis_client", None)


def test_get_redis_creates_client_lazily(monkeypatch):
    expected_client = object()
    calls = []

    def fake_from_url(url, **kwargs):
        calls.append((url, kwargs))
        return expected_client

    monkeypatch.setattr(
        cache.redis.Redis,
        "from_url",
        fake_from_url,
    )

    first = cache.get_redis()
    second = cache.get_redis()

    assert first is expected_client
    assert second is expected_client
    assert len(calls) == 1

    url, options = calls[0]
    assert url == cache.settings.redis_url
    assert options["decode_responses"] is True
    assert options["socket_connect_timeout"] == 0.2
    assert options["socket_timeout"] == 0.2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5),
        ("0", 0),
        (None, 0),
    ],
)
def test_get_plan_cache_generation_success(
    monkeypatch,
    value,
    expected,
):
    fake = FakeRedis(value=value)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_plan_cache_generation() == expected
    assert fake.get_calls == [
        cache.PLAN_CACHE_GENERATION_KEY
    ]


@pytest.mark.parametrize(
    "error",
    [
        redis.RedisError("Redis error"),
        OSError("Connection error"),
        ValueError("Invalid generation"),
    ],
)
def test_get_plan_cache_generation_failure(
    monkeypatch,
    error,
):
    fake = FakeRedis(error=error)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_plan_cache_generation() is None


def test_get_json_returns_dictionary(monkeypatch):
    fake = FakeRedis(value='{"name":"Unlimited","price":299}')
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_json("plans:1") == {
        "name": "Unlimited",
        "price": 299,
    }


def test_get_json_returns_none_for_missing_key(monkeypatch):
    fake = FakeRedis(value=None)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_json("missing") is None


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        '["one", "two"]',
        '"plain string"',
        "123",
        "null",
    ],
)
def test_get_json_rejects_invalid_or_non_dictionary_values(
    monkeypatch,
    value,
):
    fake = FakeRedis(value=value)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_json("bad-value") is None


def test_get_json_handles_redis_error(monkeypatch):
    fake = FakeRedis(error=redis.RedisError("Redis unavailable"))
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_json("plans") is None


def test_get_json_handles_type_error(monkeypatch):
    fake = FakeRedis(value=object())
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.get_json("plans") is None


def test_set_json_stores_value_with_configured_ttl(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    result = cache.set_json(
        "plans:1",
        {"name": "Unlimited"},
    )

    assert result is True
    assert fake.set_calls == [
        (
            "plans:1",
            json.dumps({"name": "Unlimited"}),
            cache.settings.plan_cache_ttl_seconds,
        )
    ]


@pytest.mark.parametrize(
    "error",
    [
        redis.RedisError("Redis unavailable"),
        OSError("Connection failed"),
    ],
)
def test_set_json_handles_redis_failures(monkeypatch, error):
    fake = FakeRedis(error=error)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.set_json("plans:1", {"name": "Plan"}) is False


def test_set_json_handles_serialization_type_error(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.set_json("plans:1", {"bad": object()}) is False


def test_invalidate_plan_cache_increments_generation(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.invalidate_plan_cache() is True
    assert fake.incr_calls == [
        cache.PLAN_CACHE_GENERATION_KEY
    ]


@pytest.mark.parametrize(
    "error",
    [
        redis.RedisError("Redis unavailable"),
        OSError("Connection failed"),
    ],
)
def test_invalidate_plan_cache_handles_failures(
    monkeypatch,
    error,
):
    fake = FakeRedis(error=error)
    monkeypatch.setattr(cache, "get_redis", lambda: fake)

    assert cache.invalidate_plan_cache() is False


def test_plan_list_cache_key_is_deterministic():
    first = cache.build_plan_list_cache_key(
        1, "unlimited", 50000, 1024, 1, 10
    )
    second = cache.build_plan_list_cache_key(
        1, "unlimited", 50000, 1024, 1, 10
    )

    assert first == second


def test_plan_list_cache_key_changes_with_filters():
    original = cache.build_plan_list_cache_key(
        1, "unlimited", 50000, 1024, 1, 10
    )
    changed = cache.build_plan_list_cache_key(
        1, "unlimited", 50000, 1024, 2, 10
    )

    assert original != changed


def test_plan_list_cache_key_changes_with_generation():
    first = cache.build_plan_list_cache_key(
        1, None, None, None, 1, 10
    )
    second = cache.build_plan_list_cache_key(
        2, None, None, None, 1, 10
    )

    assert first != second


def test_plan_detail_cache_key():
    assert cache.build_plan_detail_cache_key(3, 42) == (
        "telecom:plans:v1:g3:detail:42"
    )
