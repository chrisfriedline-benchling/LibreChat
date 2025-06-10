from __future__ import annotations

import re
from collections import namedtuple
from dataclasses import dataclass

WarehouseRelationship = namedtuple(
    "WarehouseRelationship",
    ["from_table_name", "from_column_name", "target_table_name", "target_column_name"],
)


@dataclass
class TableColumn:
    name: str
    data_type: str
    is_multi: bool
    display_name: str | None = None
    samples: list[str] | None = None
    tooltip: str | None = None


@dataclass
class TableInfo:
    org_prefix: str
    table_name: str
    columns: list[TableColumn]
    schema_name: str | None  # e.g. "Run Schema", "Result Schema"
    relationships: list[WarehouseRelationship]


# Columns that end in "_id", "_id$", "_uuid", "_uuid$" are presumed IDs
ID_COLUMN_REGEX = re.compile(r"_(?:uu)?id\$?$", re.IGNORECASE)
AVERAGE_CHARS_PER_SAMPLE = 20


def _truncate_sample(sample: str, limit: int) -> str:
    if len(sample) > limit:
        return sample[:limit] + "[…]"
    return sample


def _truncate_samples(samples: list[str], limit: int) -> list[str]:
    return [_truncate_sample(sample, limit) for sample in samples]


def _select_column_samples(column: TableColumn) -> list[str]:  # noqa:PLR0911
    if column.samples is None or len(column.samples) == 0:
        return []

    if column.is_multi or column.data_type.startswith("json"):
        # bias towards shorter samples to reduce the likelihood of truncation
        sorted_samples = sorted(column.samples, key=len)
        return _truncate_samples(
            sorted_samples[:4], 500
        )  # worst case ~500 tokens per json column
    if column.data_type.startswith("timestamp") or column.data_type == "date":
        return column.samples[:1]
    if column.data_type == "character varying":
        # try to detect if this column is storing IDs and if so provide fewer
        if column.name == "id" or ID_COLUMN_REGEX.search(column.name) is not None:
            return column.samples[:2]
        # scale the number of varchar samples relative to the average size of the items
        # this is loosely to encourage more samples of short enum like values,
        # and fewer of UGC like names or URLs
        average_chars = sum(len(str(s)) for s in column.samples) / len(column.samples)
        if average_chars > AVERAGE_CHARS_PER_SAMPLE:
            # bias towards shorter samples to reduce the likelihood of truncation
            sorted_samples = sorted(column.samples, key=len)
            return _truncate_samples(sorted_samples[:2], 150)
        return _truncate_samples(column.samples[:5], 50)
    # double precision | numeric | integer | boolean
    return []


def _short_data_type(data_type: str) -> str:
    if data_type.startswith("character varying"):
        return "varchar"
    # The SQL standard requires that writing just timestamp be equivalent to timestamp
    # without time zone, and PostgreSQL honors that behavior.
    if data_type.startswith("timestamp without time zone"):
        return "timestamp"
    return data_type


def _friendly_relationship(relationship: WarehouseRelationship, org_prefix: str) -> str:
    return f"{relationship.from_column_name} column has a relationship with the \
{relationship.target_column_name} column \
from {org_prefix}.{relationship.target_table_name}\n"


def _is_novel_display_name(column: TableColumn) -> bool:
    if column.display_name is None:
        return False
    normalized_display_name = (
        column.display_name.lower().replace(" ", "_").replace("-", "_")
    )
    return normalized_display_name != column.name


def _format_column(
    column: TableColumn, include_type: bool, include_samples: bool
) -> str:
    if include_type:
        column_description = f"{column.name} ({_short_data_type(column.data_type)})"
    else:
        column_description = column.name

    if _is_novel_display_name(column):
        column_description += f" [also known as {column.display_name}]"

    if column.tooltip is not None and len(column.tooltip) > 0:
        column_description += f" [description: {column.tooltip}]"

    if include_samples:
        selected_samples = _select_column_samples(column)
        if len(selected_samples) > 0:
            stringified_samples = " | ".join(selected_samples)
            column_description += f" e.g. {stringified_samples}"

    return column_description


def describe_table_to_llm(
    table_info: TableInfo,
    include_col_names: bool = False,
    include_col_types: bool = False,
    include_col_samples: bool = False,
    include_relationships: bool = False,
) -> str:
    prefixed_table_name = f"{table_info.org_prefix}.{table_info.table_name}"
    table_schema_type = (
        "" if table_info.schema_name is None else f" (type: {table_info.schema_name})"
    )

    if not include_col_names and not include_col_types and not include_relationships:
        return f"{prefixed_table_name}{table_schema_type}"

    table_description = f"{prefixed_table_name}{table_schema_type}"

    if include_col_names:
        table_description += "\n\n<columns>\n"
        table_description += "\n".join(
            _format_column(column, include_col_types, include_col_samples)
            for column in table_info.columns
        )
        table_description += "\n</columns>"

    if include_relationships:
        outward_relationships = [
            r
            for r in table_info.relationships
            if r.from_table_name == table_info.table_name
        ]
        if len(outward_relationships) > 0:
            table_description += "\n\n<outward relationships>\n"
            for relationship in outward_relationships:
                table_description += _friendly_relationship(
                    relationship, table_info.org_prefix
                )
            table_description += "\n</outward relationships>"
    return f"<table>\n{table_description.strip()}\n</table>"
