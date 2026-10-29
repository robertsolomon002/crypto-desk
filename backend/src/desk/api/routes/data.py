"""`/api/data` routes: list the allowlisted tables, query one with filters and paging, export
CSV (D37). Every filter is a bound parameter on an allowlisted column; values are cast to the
column's type first."""

import csv
import datetime as dt
import io
from collections.abc import Iterator
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Column, Select, Text, any_, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from desk.api.deps import CurrentUser, SessionDep, UserDep, open_session, require_role
from desk.api.schemas import Envelope, Source
from desk.api.tables import TABLES, TableSpec

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(require_role("member"))])

MAX_PAGE_SIZE = 500
MAX_EXPORT_ROWS = 200_000
OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ColumnInfo(BaseModel):
    name: str
    type: str
    filterable: bool


class TableInfo(BaseModel):
    name: str
    description: str
    visibility: Literal["member", "own", "admin"]
    rows: int
    last_updated: str | None
    columns: list[ColumnInfo]


class TablePage(BaseModel):
    table: str
    columns: list[str]
    total: int
    page: int
    page_size: int
    rows: list[dict[str, Any]]


def _spec(name: str, user: CurrentUser) -> TableSpec:
    spec = TABLES.get(name)
    if spec is None or not spec.visible_to(user.is_admin):
        raise HTTPException(404, f"unknown table {name!r}")
    return spec


def _filterable(col: Column) -> bool:
    return not isinstance(col.type, JSONB)


def _cast(col: Column, raw: str) -> Any:
    if isinstance(col.type, ARRAY):
        return raw
    try:
        kind = col.type.python_type
    except NotImplementedError:
        return raw
    try:
        if kind is bool:
            if raw.lower() not in ("true", "false"):
                raise ValueError(raw)
            return raw.lower() == "true"
        if kind is dt.datetime:
            value = dt.datetime.fromisoformat(raw)
            return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
        if kind in (dt.date, dt.time):
            return kind.fromisoformat(raw)
        if kind is Decimal:
            return Decimal(raw)
        return kind(raw)
    except (ValueError, ArithmeticError):
        raise HTTPException(400, f"bad value for {col.name}") from None


def _where(spec: TableSpec, user: CurrentUser, filters: list[str]) -> list:
    cols = {c.name: c for c in spec.columns()}
    clauses = []
    if spec.visibility == "own" and not user.is_admin:
        clauses.append(spec.table.c[spec.owner] == user.id)
    for f in filters:
        name, op, raw = (f.split(":", 2) + ["", ""])[:3]
        col = cols.get(name)
        if col is None or not _filterable(col):
            raise HTTPException(400, f"cannot filter on {name!r}")
        if op not in OPS:
            raise HTTPException(400, f"unknown filter op {op!r}; use one of {', '.join(OPS)}")
        if isinstance(col.type, ARRAY):
            if op != "contains":
                raise HTTPException(400, f"{name} supports only 'contains'")
            clauses.append(any_(col) == raw)
            continue
        if op == "contains":
            clauses.append(cast(col, Text).contains(raw, autoescape=True))
            continue
        value = _cast(col, raw)
        clauses.append(
            {"eq": col == value, "ne": col != value, "gt": col > value, "gte": col >= value,
             "lt": col < value, "lte": col <= value}[op]
        )  # fmt: skip
    return clauses


def _query(
    spec: TableSpec, user: CurrentUser, filters: list[str], order: str | None, desc: bool
) -> Select:
    cols = spec.columns()
    stmt = select(*cols).where(*_where(spec, user, filters))
    if order is not None:
        col = {c.name: c for c in cols}.get(order)
        if col is None or not _filterable(col):
            raise HTTPException(400, f"cannot order by {order!r}")
        return stmt.order_by(col.desc() if desc else col.asc())
    pk = list(spec.table.primary_key.columns)
    return stmt.order_by(*[c.desc() if desc else c.asc() for c in pk])


FilterQuery = Annotated[
    list[str] | None,
    Query(alias="filter", description="column:op:value, repeatable; ops: " + ", ".join(OPS)),
]


@router.get("/tables", response_model=Envelope[list[TableInfo]], operation_id="listTables")
def list_tables(session: SessionDep, user: UserDep) -> Envelope[list[TableInfo]]:
    """Every table this user may browse, with row counts and freshness."""
    out = []
    for spec in TABLES.values():
        if not spec.visible_to(user.is_admin):
            continue
        t = spec.table
        stmt = select(func.count()).select_from(t).where(*_where(spec, user, []))
        if spec.fresh:
            stmt = stmt.add_columns(func.max(t.c[spec.fresh]))
        row = session.execute(stmt).one()
        fresh = row[1] if spec.fresh else None
        out.append(
            TableInfo(
                name=spec.name,
                description=spec.description,
                visibility=spec.visibility,
                rows=row[0],
                last_updated=fresh.isoformat() if fresh is not None else None,
                columns=[
                    ColumnInfo(name=c.name, type=str(c.type), filterable=_filterable(c))
                    for c in spec.columns()
                ],  # fmt: skip
            )
        )
    return Envelope(as_of=dt.datetime.now(dt.UTC).date(), sources=[Source(name="database")],
                    data=out)  # fmt: skip


@router.get("/tables/{name}", response_model=Envelope[TablePage], operation_id="queryTable")
def query_table(
    name: str,
    session: SessionDep,
    user: UserDep,
    filters: FilterQuery = None,
    order: str | None = None,
    desc: bool = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 100,
) -> Envelope[TablePage]:
    """One page of a table. Default order: primary key, newest first."""
    spec = _spec(name, user)
    stmt = _query(spec, user, filters or [], order, desc)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = session.execute(stmt.limit(page_size).offset((page - 1) * page_size)).mappings()
    data = TablePage(
        table=spec.name,
        columns=[c.name for c in spec.columns()],
        total=total or 0,
        page=page,
        page_size=page_size,
        rows=jsonable_encoder([dict(r) for r in rows]),
    )
    src = Source(name="database", detail=spec.name)
    return Envelope(as_of=dt.datetime.now(dt.UTC).date(), sources=[src], data=data)


def csv_cell(value: Any) -> Any:
    """Neutralize spreadsheet formulas in untrusted text (OWASP CSV injection)."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    if isinstance(value, list | dict):
        return csv_cell(str(jsonable_encoder(value)))
    return value


def _csv_rows(stmt: Select, header: list[str]) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    # The request session is closed once the dependency exits, so stream from a fresh one.
    with open_session() as session:
        for row in session.execute(stmt.limit(MAX_EXPORT_ROWS).execution_options(yield_per=1000)):
            writer.writerow([csv_cell(v) for v in row])
            if buf.tell() > 64_000:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
    yield buf.getvalue()


@router.get(
    "/tables/{name}/export.csv",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}}},
    operation_id="exportTable",
)
def export_table(
    name: str,
    user: UserDep,
    filters: FilterQuery = None,
    order: str | None = None,
    desc: bool = True,
) -> StreamingResponse:
    """The filtered table as CSV (at most 200,000 rows)."""
    spec = _spec(name, user)
    stmt = _query(spec, user, filters or [], order, desc)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    return StreamingResponse(
        _csv_rows(stmt, [c.name for c in spec.columns()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{spec.name}_{stamp}.csv"'},
    )
