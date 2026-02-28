"""Schema caching layer — avoids hammering service APIs on every verification."""

from __future__ import annotations

import hashlib
import json
import time

from workflow_verify.ast.models import Schema


def _hash_credentials(credentials: dict) -> str:
    """Create a stable hash of credentials for cache key generation."""
    raw = json.dumps(credentials, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class SchemaCache:
    """In-memory TTL cache for resolved schemas.

    Cache key format: "{service}:{object_type}:{credentials_hash}"
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._cache: dict[str, tuple[Schema, float]] = {}
        self.ttl = ttl_seconds

    def _make_key(self, service: str, object_type: str, credentials: dict) -> str:
        cred_hash = _hash_credentials(credentials)
        return f"{service}:{object_type}:{cred_hash}"

    def get(self, service: str, object_type: str, credentials: dict) -> Schema | None:
        """Return cached schema if not expired, else None."""
        key = self._make_key(service, object_type, credentials)
        entry = self._cache.get(key)
        if entry is None:
            return None
        schema, timestamp = entry
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            return None
        return schema

    def set(self, service: str, object_type: str, credentials: dict, schema: Schema) -> None:
        """Cache a schema with the current timestamp."""
        key = self._make_key(service, object_type, credentials)
        self._cache[key] = (schema, time.time())

    def invalidate(self, key: str | None = None) -> None:
        """Clear one key (format 'service:object_type:hash') or entire cache."""
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def invalidate_service(self, service: str) -> None:
        """Clear all cached schemas for a specific service."""
        to_remove = [k for k in self._cache if k.startswith(f"{service}:")]
        for k in to_remove:
            del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)
