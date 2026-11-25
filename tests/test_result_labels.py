"""结果表头及旧会话读取的回归测试。"""

from fastapi.testclient import TestClient

import config
import main
from nl2sql.history import ConversationStore
from nl2sql.result_labels import query_column_labels
from nl2sql.schemas import ExecSummary, QueryResult


_QUERY = """SELECT SUM(CASE WHEN a.org_no = '001' THEN a.loan_bal_rmb ELSE 0 END) AS amount
            FROM ads.corp_cust_loan_bal_d a WHERE a.data_dt = DATE '2026-09-30'"""


def test_conditional_aggregate_labels_the_amount_not_the_condition(mock_store) -> None:
    """条件聚合的列名只使用结果字段的中文名。"""
    amount = mock_store.column("ads.corp_cust_loan_bal_d", "loan_bal_rmb").column_cn
    assert query_column_labels(_QUERY, mock_store) == [f"{amount}合计"]


def test_reading_a_legacy_result_supplies_labels_without_updating_history(tmp_path, monkeypatch, mock_store) -> None:
    """未保存展示列名的旧结果可以显示中文，原始列名、值和 SQLite 记录保持一致。"""
    history = ConversationStore(tmp_path / "history.db")
    conversation = history.create()
    history.add_turn(conversation.id, "看余额", QueryResult(
        status="ok", question="看余额", sql=_QUERY,
        exec_result=ExecSummary(executed=True, columns=["amount"], rows=[[100]], row_count=1),
    ))
    monkeypatch.setattr(config, "ACCESS_CONTROL_ENABLED", False)
    monkeypatch.setattr(main, "_active_store", lambda: mock_store)
    monkeypatch.setitem(main.app.dependency_overrides, main.get_history_dep, lambda: history)

    response = TestClient(main.app).get(f"/conversations/{conversation.id}")
    assert response.status_code == 200
    result = response.json()["turns"][0]["result"]["exec_result"]
    assert result["columns"] == ["amount"] and result["rows"] == [[100]]
    assert result["column_labels"] == query_column_labels(_QUERY, mock_store)
    assert not history.get(conversation.id).turns[0].result["exec_result"].get("column_labels")
