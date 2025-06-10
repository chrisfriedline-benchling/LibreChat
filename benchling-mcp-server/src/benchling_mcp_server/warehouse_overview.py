from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.pool
from psycopg2.extensions import cursor

from .llm_friendly_table import TableColumn, TableInfo, WarehouseRelationship

# These columns exist for internal use, and shouldn't be used in any query.
# See https://docs.benchling.com/docs/warehouse-tables-v2
EXCLUDED_COLUMNS = {"_pkey", "_sync_key", "acl_resource_id", "source_id"}


@dataclass
class WarehouseOverview:
    table_info: dict[str, TableInfo]


def get_warehouse_overview(
    db_pool: psycopg2.pool.SimpleConnectionPool, org_prefix: str
) -> WarehouseOverview:
    with db_pool.getconn() as conn:
        with conn.cursor() as cur:
            schemas = _get_schemas(cur, org_prefix)
            schema_fields = _get_schema_fields(cur, org_prefix)
            samples = _get_samples(cur, org_prefix)
            schema_relationships = _get_schema_relationships(cur, org_prefix)

            # Skip views since all data is in the raw tables
            tables = _run_query(
                cur,
                f"""
                SELECT table_schema, table_name FROM information_schema.tables
                WHERE table_schema = '{org_prefix}'
                AND table_type != 'VIEW'
            """,
            )
            table_info = {}
            columns = defaultdict(list)
            for table_name, column_name, data_type in _run_query(
                cur,
                f"""SELECT columns.table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{org_prefix}'""",
            ):
                columns[table_name].append((column_name, data_type))

            for table_schema, table_name in tables:
                schema_system_name = table_name.replace("$raw", "")
                schema_id, schema_type = next(
                    (
                        (schema_id, schema_type)
                        for schema_id, (system_name, schema_type) in schemas.items()
                        if system_name == schema_system_name
                    ),
                    (None, None),
                )
                this_schema_fields = schema_fields.get(schema_id, {})
                table_columns = []
                for column_name, data_type in columns[table_name]:
                    if column_name in EXCLUDED_COLUMNS:
                        continue
                    schema_field_name, is_multi, tooltip = this_schema_fields.get(
                        column_name, (None, False, None)
                    )
                    table_columns.append(
                        TableColumn(
                            name=column_name,
                            display_name=schema_field_name,
                            data_type=data_type,
                            is_multi=is_multi,
                            tooltip=tooltip,
                            samples=samples.get(schema_id, {}).get(column_name),
                        )
                    )

                relationships = []
                for column_name, target_schema_id in schema_relationships.get(
                    schema_id, []
                ):
                    # Target schema may not be visible
                    if target_schema_id not in schemas:
                        continue
                    target_schema_name, _ = schemas[target_schema_id]
                    relationships.append(
                        WarehouseRelationship(
                            from_table_name=table_name,
                            from_column_name=column_name,
                            target_table_name=f"{target_schema_name}$raw",
                            target_column_name="id",
                        )
                    )

                table_info[table_name] = TableInfo(
                    org_prefix=table_schema,
                    table_name=table_name,
                    columns=table_columns,
                    schema_name=schema_type,
                    relationships=relationships,
                )

            return WarehouseOverview(table_info=table_info)


def _run_query(cur: cursor, query: str) -> Any:
    cur.execute(query)
    return cur.fetchall()


def _get_schemas(cur: cursor, org_prefix: str) -> dict:
    schemas = {}
    for schema_id, system_name, schema_type in _run_query(
        cur, f'SELECT id, system_name, schema_type FROM "{org_prefix}"."schema$raw"'
    ):
        schemas[schema_id] = (system_name, schema_type)
    return schemas


def _get_schema_fields(cur: cursor, org_prefix: str) -> dict:
    all_schema_fields: dict[str, dict] = defaultdict(dict)
    for schema_id, system_name, name, is_multi, tooltip in _run_query(
        cur,
        f"""SELECT schema_id, system_name, name, is_multi, tooltip
            FROM "{org_prefix}"."schema_field$raw"
        """,
    ):
        all_schema_fields[schema_id][system_name] = (name, is_multi, tooltip)
    return all_schema_fields


def _get_samples(cur: cursor, org_prefix: str) -> dict:
    sampled_entities: dict[str, dict] = {}
    sample_rows = _run_query(
        cur,
        f"""
        WITH RankedItems AS (
            SELECT
                id,
                name,
                file_registry_id,
                schema_id,
                ROW_NUMBER() OVER (PARTITION BY schema_id ORDER BY created_at DESC) AS rn
            FROM "{org_prefix}"."entity$raw"
            WHERE schema_id IS NOT NULL AND file_registry_id IS NOT NULL
        )
        SELECT schema_id, id, name, file_registry_id
        FROM RankedItems
        WHERE rn <= 3;
    """,  # noqa:E501
    )
    for schema_id, id, name, file_registry_id in sample_rows:
        if schema_id not in sampled_entities:
            sampled_entities[schema_id] = {
                "id": [],
                "name$": [],
                "file_registry_id$": [],
            }
        sampled_entities[schema_id]["id"].append(id)
        sampled_entities[schema_id]["name$"].append(name)
        sampled_entities[schema_id]["file_registry_id$"].append(file_registry_id)
    return sampled_entities


def _get_schema_relationships(cur: cursor, org_prefix: str) -> dict:
    schema_relationships = defaultdict(list)
    relationship_rows = _run_query(
        cur,
        f"""
        SELECT schema_id, system_name, target_schema_id
        FROM "{org_prefix}"."field_definition$raw"
        WHERE target_schema_id IS NOT NULL
    """,
    )
    for schema_id, system_name, target_schema_id in relationship_rows:
        schema_relationships[schema_id].append((system_name, target_schema_id))
    return schema_relationships
