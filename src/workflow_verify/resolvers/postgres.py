"""PostgreSQL information_schema resolver."""

from __future__ import annotations

import os
from typing import Any

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver

POSTGRES_TYPE_MAP: dict[str, WFType] = {
    "text": WFType.TEXT,
    "character varying": WFType.TEXT,
    "varchar": WFType.TEXT,
    "character": WFType.TEXT,
    "char": WFType.TEXT,
    "integer": WFType.INT,
    "bigint": WFType.INT,
    "smallint": WFType.INT,
    "serial": WFType.INT,
    "bigserial": WFType.INT,
    "numeric": WFType.FLOAT,
    "decimal": WFType.FLOAT,
    "real": WFType.FLOAT,
    "double precision": WFType.FLOAT,
    "boolean": WFType.BOOL,
    "date": WFType.DATE,
    "timestamp without time zone": WFType.DATETIME,
    "timestamp with time zone": WFType.DATETIME,
    "jsonb": WFType.JSON,
    "json": WFType.JSON,
    "uuid": WFType.TEXT,
    "bytea": WFType.TEXT,
    "inet": WFType.TEXT,
    "cidr": WFType.TEXT,
    "macaddr": WFType.TEXT,
    "interval": WFType.TEXT,
    "time without time zone": WFType.TEXT,
    "time with time zone": WFType.TEXT,
    "money": WFType.FLOAT,
    "xml": WFType.TEXT,
    "array": WFType.JSON,
    "user-defined": WFType.TEXT,
}


class PostgresResolver(SchemaResolver):
    """Resolves schemas from PostgreSQL information_schema.

    Queries information_schema.columns for a given table to discover
    all columns and their types.
    """

    service_name = "postgres"

    def supported_objects(self) -> list[str]:
        return []  # Dynamic — depends on the database

    def env_var_names(self) -> list[str]:
        return ["DATABASE_URL"]

    def map_type(self, service_type: str) -> WFType:
        return POSTGRES_TYPE_MAP.get(service_type.lower(), WFType.TEXT)

    def _get_dsn(self, credentials: dict) -> str:
        dsn = credentials.get("database_url") or credentials.get("dsn")
        if not dsn:
            dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise SchemaResolveError(
                "PostgreSQL connection string required. Provide 'database_url' "
                "in credentials or set DATABASE_URL environment variable."
            )
        return dsn

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        dsn = self._get_dsn(credentials)

        # Parse table name — support schema.table format
        parts = object_type.split(".")
        if len(parts) == 2:
            schema_name, table_name = parts
        else:
            schema_name, table_name = "public", object_type

        try:
            import asyncpg
        except ImportError:
            raise SchemaResolveError(
                "asyncpg package required for PostgreSQL resolver. "
                "Install with: pip install asyncpg"
            )

        try:
            conn = await asyncpg.connect(dsn)
        except Exception as e:
            raise SchemaResolveError(
                f"Failed to connect to PostgreSQL: {e}"
            )

        try:
            rows = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default,
                       udt_name
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
                """,
                schema_name,
                table_name,
            )
        except Exception as e:
            raise SchemaResolveError(
                f"Failed to query information_schema for '{object_type}': {e}"
            )
        finally:
            await conn.close()

        if not rows:
            raise SchemaResolveError(
                f"Table '{object_type}' not found or has no columns."
            )

        return self._parse_columns(rows, object_type)

    def _parse_columns(self, rows: list[Any], table_name: str) -> Schema:
        fields: list[FieldDef] = []
        for row in rows:
            col_name = row["column_name"]
            data_type = row["data_type"]
            nullable = row["is_nullable"] == "YES"

            field_type = self.map_type(data_type)
            description = f"type: {data_type}"
            if nullable:
                description += ", nullable"

            fields.append(
                FieldDef(
                    name=col_name,
                    type=field_type,
                    description=description,
                )
            )

        clean_name = table_name.replace(".", "_").title().replace("_", "")
        return Schema(
            name=f"Postgres{clean_name}",
            fields=fields,
            description=f"Live schema from PostgreSQL table '{table_name}'",
        )
