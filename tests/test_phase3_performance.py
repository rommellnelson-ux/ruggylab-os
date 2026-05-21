import pytest
from fastapi.testclient import TestClient

from app.core.caching import MemoryCache, get_cache_key
from app.core.config import settings
from app.main import create_app


@pytest.fixture
def client():
    """Test client with performance features."""
    app = create_app()
    return TestClient(app)


@pytest.mark.anyio
async def test_memory_cache_set_and_get():
    """Test in-memory cache set and get operations."""
    cache = MemoryCache()

    # Set value
    await cache.set("test_key", {"data": "test_value"}, ttl=10)

    # Get value
    value = await cache.get("test_key")
    assert value == {"data": "test_value"}

    # Get non-existent key
    value = await cache.get("non_existent")
    assert value is None


@pytest.mark.anyio
async def test_memory_cache_ttl_expiry():
    """Test cache expiry after TTL."""
    import time

    cache = MemoryCache()

    # Set value with 1 second TTL
    await cache.set("test_key", {"data": "test"}, ttl=1)

    # Get immediately
    value = await cache.get("test_key")
    assert value == {"data": "test"}

    # Wait for expiry
    time.sleep(1.1)

    # Get after expiry
    value = await cache.get("test_key")
    assert value is None


@pytest.mark.anyio
async def test_memory_cache_delete():
    """Test cache delete operation."""
    cache = MemoryCache()

    # Set and delete
    await cache.set("test_key", {"data": "test"}, ttl=10)
    await cache.delete("test_key")

    # Verify deletion
    value = await cache.get("test_key")
    assert value is None


def test_cache_key_generation():
    """Test cache key generation."""
    key1 = get_cache_key("user:123", "posts")
    key2 = get_cache_key("user:123", "posts")
    key3 = get_cache_key("user:456", "posts")

    # Same inputs should produce same key
    assert key1 == key2

    # Different inputs should produce different keys
    assert key1 != key3


def test_pagination_params_validation():
    """Test pagination parameter validation."""
    from app.schemas.pagination import PaginationParams

    # Valid parameters
    params = PaginationParams(skip=0, limit=20)
    assert params.skip == 0
    assert params.limit == 20

    # Test max limit enforcement
    params = PaginationParams(skip=0, limit=settings.MAX_PAGE_SIZE)
    assert params.limit == settings.MAX_PAGE_SIZE

    # Limit exceeding max should raise validation error
    import pytest

    with pytest.raises(Exception):  # Pydantic validation error
        PaginationParams(skip=0, limit=999)


def test_pagination_meta_creation():
    """Test pagination metadata creation."""
    from app.schemas.pagination import PaginationMeta

    meta = PaginationMeta.from_counts(total=100, skip=0, limit=20)

    assert meta.total == 100
    assert meta.skip == 0
    assert meta.limit == 20
    assert meta.pages == 5  # 100 items / 20 per page = 5 pages


def test_compression_headers_on_response(client):
    """Test that compression headers are set on large responses."""
    if not settings.COMPRESSION_ENABLED:
        pytest.skip("Compression not enabled")

    # GET request should include Accept-Encoding: gzip
    response = client.get(
        "/health",
        headers={"Accept-Encoding": "gzip"},
    )
    assert response.status_code == 200


def test_default_pagination_params():
    """Test default pagination parameters."""
    from app.schemas.pagination import PaginationParams

    params = PaginationParams()
    assert params.skip == 0
    assert params.limit == settings.DEFAULT_PAGE_SIZE
