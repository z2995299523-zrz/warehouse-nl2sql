"""按查询输出的位置从元数据生成中文展示列名。"""

import logging
import re
from collections.abc import Sequence

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from metadata.models import FieldRef
from metadata.sqlscope import Catalog, ScopeResolver, parse_statements, qualify_with_catalog

logger = logging.getLogger(__name__)
_CHINESE = re.compile(r"[\u3400-\u9fff]")
_FUNCTION_LABELS = {"count": "计数", "sum": "合计", "avg": "平均值", "min": "最小值", "max": "最大值",
                    "row_number": "行号", "rank": "排名", "dense_rank": "排名"}


def _field_names(refs: set[FieldRef] | frozenset[FieldRef], catalog: Catalog) -> list[str]:
    """按来源取字段中文名，按表和字段排序并去重。"""
    names = []
    for ref in sorted(refs, key=lambda item: (item.table, item.column)):
        meta = next((col for col in catalog.columns(ref.table) if col.column_name == ref.column), None)
        name = meta.column_cn.strip() if meta else ""
        if _CHINESE.search(name) and name not in names:
            names.append(name)
    return names


def column_name(column: exp.Column, scope: Scope, resolver: ScopeResolver, catalog: Catalog) -> str:
    """从字段来源取展示名，保留查询内部已定义的中文字段名。"""
    resolution = resolver.resolve_column(scope, column)
    names = _field_names(resolution.sources, catalog)
    if not names and not column.table:
        names = _field_names({ref for alias in resolver.owners(scope, column.name) for ref in resolver.resolve_column(
            scope, exp.column(column.name, table=alias)).sources}, catalog)
    if _CHINESE.search(column.name) and resolution.kind != "passthrough":
        return column.name
    return "、".join(names) or column.name


def _value_columns(node: exp.Expression) -> exp.Expression:
    """展示列名取计算值的来源，忽略条件、分区和排序表达式。"""
    if isinstance(node, (exp.Window, exp.Filter)):
        return node.this.transform(_value_columns, copy=False)
    if isinstance(node, exp.Case):
        branches = [branch.args["true"] for branch in node.args.get("ifs", ())]
        if node.args.get("default") is not None:
            branches.append(node.args["default"])
        return exp.Tuple(expressions=[branch.transform(_value_columns, copy=False) for branch in branches])
    return node


def projection_label(projection: exp.Expression, scope: Scope, resolver: ScopeResolver, catalog: Catalog) -> str:
    """使用已有中文别名，或按字段来源和聚合方式生成展示名。"""
    if _CHINESE.search(projection.output_name):
        return projection.output_name
    value = projection.unalias().unnest()
    if isinstance(value, exp.Column):
        name = column_name(value, scope, resolver, catalog)
        return name if _CHINESE.search(name) else ""
    value = value.transform(_value_columns)
    operation = _FUNCTION_LABELS.get(value.key, "")
    names = _field_names(resolver.resolve_expression(scope, value).sources, catalog)
    if value.key == "sum" and len(names) == 1 and names[0].startswith(("本月总", "当月总")):
        return names[0][2:]
    return "、".join(names) + operation if operation else (f"{'、'.join(names)}计算值" if names else "")


def projection_labels(root: Scope, query: exp.Expression, catalog: Catalog) -> list[str]:
    """解析最外层输出列表，星号展开后按实际输出顺序生成列名。"""
    output = root
    if any(item.is_star for item in root.expression.selects):
        output = build_scope(qualify_with_catalog(query, catalog)[0])
    if output is None:
        return []
    resolver = ScopeResolver(output, catalog=catalog)
    while output.union_scopes:
        output = output.union_scopes[0]
    return [projection_label(item, output, resolver, catalog) for item in output.expression.selects]


def query_column_labels(sql: str, catalog: Catalog) -> list[str]:
    """从一条查询提取展示列名，解析失败时交给调用方回退。"""
    try:
        query, = parse_statements(sql)
        root = build_scope(query)
        return projection_labels(root, query, catalog) if root is not None else []
    except Exception:  # noqa: BLE001 展示名推断异常不影响原查询和会话读取
        logger.debug("无法推断查询结果的中文列名")
        return []


def result_column_labels(columns: Sequence[str], labels: Sequence[str]) -> list[str]:
    """按位置对应结果列，缺少名称时用中文列号和数据库原始列名。"""
    if len(columns) != len(labels):
        labels = [""] * len(columns)
    result = []
    for i, (name, label) in enumerate(zip(columns, labels), 1):
        fallback = f"结果列 {i}（{name}）" if name else f"结果列 {i}"
        result.append(label or (name if _CHINESE.search(name) else fallback))
    return result
