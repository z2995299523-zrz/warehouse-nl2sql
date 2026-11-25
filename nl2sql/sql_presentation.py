"""用元数据和 SQL 语法树补中文注释、生成执行结果的中文列名。"""
import logging

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope, walk_in_scope
from sqlglot.errors import SqlglotError

from metadata.sqlscope import (Catalog, DIALECT, ScopeResolver, conjuncts, is_table_function, parse_statements,
                               physical_tables, table_id)
from nl2sql.result_labels import column_name, projection_label, projection_labels
from nl2sql.result_labels import result_column_labels as result_column_labels

logger = logging.getLogger(__name__)
_ANNOTATIONS = ("字段", "输出", "数据表", "查询来源", "过滤条件", "分组过滤", "窗口过滤", "关联条件", "条件判断",
                "行数限制", "起始偏移")
_CLAUSES = {"where": "过滤条件", "having": "分组过滤", "qualify": "窗口过滤"}


def _annotate(node: exp.Expression, kind: str, label: str) -> None:
    """把单行说明安全地写入 SQL 块注释。"""
    text = " ".join(label.split()).replace("/*", "/ *").replace("*/", "* /")
    node.add_comments([f" {kind}：{text[:120]} "])


def _scope_notes(scope: Scope, resolver: ScopeResolver, catalog: Catalog) -> None:
    """按查询层补字段、输出表达式及每个关联键和过滤子句的说明。"""
    local = list(walk_in_scope(scope.expression))
    names = {id(node): column_name(node, scope, resolver, catalog)
             for node in local if isinstance(node, exp.Column) and not node.is_star}

    def annotate_conditions(condition: exp.Expression, kind: str, default: str) -> None:
        for part in conjuncts(condition):
            fields = dict.fromkeys(names[id(col)] for col in walk_in_scope(part) if id(col) in names)
            _annotate(part, kind, "、".join(fields) or default)

    for node in local:
        if id(node) in names:
            _annotate(node, "字段", names[id(node)])
        elif node.key in _CLAUSES:
            annotate_conditions(node.this, _CLAUSES[node.key], "保留满足此条件的记录")
        elif isinstance(node, exp.Join):
            if node.args.get("on") is not None:
                annotate_conditions(node.args["on"], "关联条件", "按此条件匹配两侧记录")
            for key in node.args.get("using") or ():
                label = column_name(exp.column(key.name), scope, resolver, catalog)
                _annotate(key, "关联条件", f"按两侧同名字段 {label} 匹配")
            if node.method == "NATURAL":
                _annotate(node, "关联条件", "按两侧所有同名字段匹配")
            elif node.kind == "CROSS":
                _annotate(node, "关联条件", "两侧记录逐一组合")
        elif isinstance(node, exp.If) and isinstance(node.parent, exp.Case):
            annotate_conditions(node.this, "条件判断", "满足条件时采用对应取值")
        elif isinstance(node, (exp.Limit, exp.Fetch)):
            _annotate(node, "行数限制", "限制返回行数")
        elif isinstance(node, exp.Offset):
            _annotate(node, "起始偏移", "跳过指定行数")

    if isinstance(scope.expression, exp.Select):
        for index, projection in enumerate(scope.expression.selects):
            if not isinstance(projection, exp.Column) or projection.is_star:
                label = projection_label(projection, scope, resolver, catalog)
                _annotate(projection, "输出", label or f"第 {index + 1} 列的取值")


def present_sql(sql: str, catalog: Catalog) -> tuple[str, list[str]]:
    """为已校验的 SQL 补展示注释和列名，注释须能无损解析回原语法树。"""
    try:
        query, = parse_statements(sql)
        root = build_scope(query)
        if root is None:
            return sql, []
        labels = projection_labels(root, query, catalog)
        resolver = ScopeResolver(root, catalog=catalog)
        for scope in root.traverse():
            _scope_notes(scope, resolver, catalog)
        physical = {id(table) for table in physical_tables(query)}
        for table in query.find_all(exp.Table):
            if id(table) in physical:
                meta = catalog.table(table_id(table))
                _annotate(table, "数据表", meta.table_cn if meta and meta.table_cn.strip() else table.name)
            else:
                label = "表函数" if is_table_function(table) else "引用上面的公用表表达式"
                _annotate(table, "查询来源", label)
        annotated = query.sql(dialect=DIALECT, pretty=True)
        return (annotated if parse_statements(annotated) == [query] else sql), labels
    except Exception:  # noqa: BLE001 展示处理异常时保留可用的原 SQL
        logger.warning("无法为查询生成中文展示说明，保留原 SQL", exc_info=True)
        return sql, []


def strip_sql_annotations(sql: str) -> str:
    """追问时从底稿去掉展示注释，保留查询结构和别名。"""
    prefixes = tuple(f"{kind}：" for kind in _ANNOTATIONS)
    if not any(f"/* {prefix}" in sql for prefix in prefixes):
        return sql
    try:
        statements = parse_statements(sql)
    except SqlglotError:
        return sql
    if len(statements) != 1:
        return sql
    query = statements[0]
    for node in query.walk():
        if node.comments:
            node.comments = [comment for comment in node.comments
                             if not comment.lstrip().startswith(prefixes)]
    return query.sql(dialect=DIALECT, pretty=True)
