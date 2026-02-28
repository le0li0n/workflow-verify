"""Dynamic schema resolvers — fetch live schemas from service APIs."""

from __future__ import annotations

import logging
from typing import Any

from workflow_verify.ast.models import Schema
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver
from workflow_verify.resolvers.cache import SchemaCache

logger = logging.getLogger(__name__)

# Global cache instance
_cache = SchemaCache()

# Resolver registry — maps service name to resolver class
_RESOLVERS: dict[str, type] = {}


def _register_resolvers() -> None:
    """Lazily register all built-in resolvers."""
    if _RESOLVERS:
        return

    from workflow_verify.resolvers.clay import ClayResolver
    from workflow_verify.resolvers.crmzero import CRMZeroResolver
    from workflow_verify.resolvers.hubspot import HubSpotResolver
    from workflow_verify.resolvers.postgres import PostgresResolver
    from workflow_verify.resolvers.salesforce import SalesforceResolver
    from workflow_verify.resolvers.stripe import StripeResolver

    for cls in [
        HubSpotResolver,
        SalesforceResolver,
        PostgresResolver,
        ClayResolver,
        CRMZeroResolver,
        StripeResolver,
    ]:
        _RESOLVERS[cls.service_name] = cls


def get_resolver(service: str) -> SchemaResolver:
    """Get a resolver instance by service name."""
    _register_resolvers()
    cls = _RESOLVERS.get(service)
    if cls is None:
        available = ", ".join(sorted(_RESOLVERS.keys()))
        raise SchemaResolveError(f"No resolver for service '{service}'. Available: {available}")
    instance: SchemaResolver = cls()
    return instance


def list_resolvers() -> list[str]:
    """List all available resolver service names."""
    _register_resolvers()
    return sorted(_RESOLVERS.keys())


async def resolve_schema(
    service: str,
    object_type: str,
    credentials: dict[str, Any] | None = None,
    include_custom: bool = True,
    fallback_to_static: bool = False,
    use_cache: bool = True,
) -> Schema:
    """Resolve a live schema from a service API.

    Tries dynamic resolution first. If it fails and fallback_to_static
    is True, falls back to the static YAML registry.

    Args:
        service: Service name (e.g. "hubspot", "salesforce", "postgres").
        object_type: Object/table type (e.g. "contacts", "Lead").
        credentials: Service-specific auth. If None, checks env vars.
        include_custom: Whether to include custom/user-defined fields.
        fallback_to_static: If True, fall back to static YAML on failure.
        use_cache: Whether to use the schema cache.

    Returns:
        A Schema model from the live service or static fallback.

    Raises:
        SchemaResolveError: If resolution fails and no fallback available.
    """
    if credentials is None:
        credentials = {}

    # Check cache first
    if use_cache:
        cached = _cache.get(service, object_type, credentials)
        if cached is not None:
            logger.debug(f"Cache hit for {service}:{object_type}")
            return cached

    # Try dynamic resolution
    resolver = get_resolver(service)
    try:
        schema = await resolver.resolve(object_type, credentials, include_custom)

        # Cache the result
        if use_cache:
            _cache.set(service, object_type, credentials, schema)

        return schema
    except SchemaResolveError as e:
        if not fallback_to_static:
            raise

        logger.info(
            f"Dynamic resolution failed for {service}:{object_type}, "
            f"falling back to static. Error: {e}"
        )

    # Fall back to static
    return _static_fallback(service, object_type)


def _static_fallback(service: str, object_type: str) -> Schema:
    """Try to find a matching static schema for the service/object."""
    from workflow_verify.registry.loader import SchemaLoadError, list_schemas, load_schema

    # Map service + object_type to likely static paths
    # e.g. ("hubspot", "contacts") -> "crm/hubspot_contact"
    object_clean = object_type.lower().rstrip("s")  # contacts -> contact
    candidates = [
        f"crm/{service}_{object_clean}",
        f"crm/{service}_{object_type.lower()}",
        f"enrichment/{service}_{object_clean}",
        f"data/{service}_{object_clean}",
        f"communication/{service}_{object_clean}",
    ]

    for candidate in candidates:
        try:
            return load_schema(candidate)
        except SchemaLoadError:
            continue

    # Search by service name as last resort
    all_paths = list_schemas()
    matching = [p for p in all_paths if service in p]
    if matching:
        return load_schema(matching[0])

    raise SchemaResolveError(
        f"No static fallback found for {service}:{object_type}. Searched: {', '.join(candidates)}"
    )


def get_cache() -> SchemaCache:
    """Get the global schema cache instance."""
    return _cache


def configure_cache(ttl_seconds: int = 300) -> None:
    """Configure the global schema cache TTL."""
    global _cache
    _cache = SchemaCache(ttl_seconds=ttl_seconds)


__all__ = [
    "SchemaResolveError",
    "SchemaResolver",
    "configure_cache",
    "get_cache",
    "get_resolver",
    "list_resolvers",
    "resolve_schema",
]
