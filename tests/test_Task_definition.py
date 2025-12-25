import os
import sys
import tempfile

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import models.Task_definition as Task_def


@pytest.fixture
def test_data_dir():
    """テストデータディレクトリのパスを返す"""
    return os.path.join(PROJECT_ROOT, "tests", "test_data")

@pytest.fixture
def sample_file(test_data_dir):
    """実際のテストファイルのパスを返す"""
    return os.path.join(test_data_dir, "test_input.txt")

@pytest.fixture
def csv_data_dir():
    """CSVファイルのディレクトリパスを返す"""
    return os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")


def test_subtask_attr_map():
    assert Task_def.SubTask.attr_map("subtask_id") == "サブID"
    assert Task_def.SubTask.attr_map("name") == "サブ名"
    assert Task_def.SubTask.attr_map("unknown") == "unknown"

def test_task_add_subtask():
    task = Task_def.Task(task_id="t1", name="テスト", order_number="o1")
    subtask = Task_def.SubTask(subtask_id="#001", name="サブ", estimated_time=10, actual_time=0,
                               is_initial=True, is_nominal=True, sort_index=1, is_incomplete=True)
    task.add_subtask(subtask)
    assert "#001" in task.sub_tasks
    assert task.sub_tasks["#001"].name == "サブ"

def test_read_task_csv(csv_data_dir):
    # 250901c3.csvを使ってread_task_csvをテスト
    csv_path = os.path.join(csv_data_dir, "250901c3.csv")
    # テストデータは必ずサブタスクが1件以上あることを前提とする
    loaded_task = Task_def.read_task_csv(csv_path)
    subtask_ids = list(loaded_task.sub_tasks.keys())
    assert "#001" in subtask_ids
    assert loaded_task.sub_tasks["#001"].name == "過去手順書発掘"


def test_read_all_task_csvs_basic(csv_data_dir):
    """CSVファイルの基本情報の読み込みテスト"""
    result = Task_def.read_all_task_csvs(csv_data_dir)

    # 3つのタスクが存在することを確認
    assert "250901c3" in result
    assert "250901d1" in result
    assert "251002a1" in result

    # タスク名とオーダー番号を確認
    assert result["250901c3"].name == "試験手順書作成"
    assert result["250901c3"].order_number == "78A-9A0201"

    assert result["250901d1"].name == "OPT-PDR-J-010"
    assert result["250901d1"].order_number == "78A-9A0102"

    assert result["251002a1"].name == "手配納期まとめ"
    assert result["251002a1"].waiting_date == "2025-01-23"

def test_read_all_task_csvs_subtasks(csv_data_dir):
    """サブタスクの読み込みテスト"""
    result = Task_def.read_all_task_csvs(csv_data_dir)

    # 250901c3のサブタスクを確認
    task_c3 = result["250901c3"]
    print("DEBUG: 250901c3 sub_tasks:", list(task_c3.sub_tasks.keys()))
    # サブタスク数はテストデータに合わせて5件
    assert len(task_c3.sub_tasks) == 5
    assert task_c3.sub_tasks["#002"].name == "文面作成"
    assert task_c3.sub_tasks["#002"].estimated_time == 60
    assert task_c3.sub_tasks["#002"].is_initial == True

    # 250901d1のサブタスクを確認
    task_d1 = result["250901d1"]
    print("DEBUG: 250901d1 sub_tasks:", list(task_d1.sub_tasks.keys()))
    # サブタスク数はテストデータに合わせて7件
    assert len(task_d1.sub_tasks) == 7
    assert task_d1.sub_tasks["#002"].name == "必要資料発掘"
    assert task_d1.sub_tasks["#002"].actual_time == 15

def test_read_all_task_csvs_dates(csv_data_dir):
    """日付フォーマットの処理テスト"""
    result = Task_def.read_all_task_csvs(csv_data_dir)

    # 251002a1の待機日を確認
    task_a1 = result["251002a1"]
    print("DEBUG: 251002a1 waiting_date:", task_a1.waiting_date)
    assert task_a1.waiting_date == "2025-01-23"

    # 250901d1の〆切日を確認
    task_d1 = result["250901d1"]
    print("DEBUG: 250901d1 sub_tasks:", list(task_d1.sub_tasks.keys()))
    # サブタスク辞書のキーから最大値（最後のサブタスクID）を取得
    last_subtask_id = sorted(task_d1.sub_tasks.keys())[-1]
    assert task_d1.sub_tasks[last_subtask_id].deadline_date == "2025-12-01"
    assert task_d1.sub_tasks[last_subtask_id].deadline_reason == "指摘票〆切1w前"

    # 250901c3の〆切日を確認
    task_c3 = result["250901c3"]
    print("DEBUG: 250901c3 sub_tasks:", list(task_c3.sub_tasks.keys()))
    last_subtask_id_c3 = sorted(task_c3.sub_tasks.keys())[-1]
    assert task_c3.sub_tasks[last_subtask_id_c3].deadline_date == "2025-11-15"
    assert task_c3.sub_tasks[last_subtask_id_c3].deadline_reason == "手順書客先提示1か月前"


def test_willdoentry_attr_map():
    entry = Task_def.WillDoEntry(
        is_done=False, project_abbr="PJ", order_abbr="ORD",
        task_id="t1", subtask_id="#001", task_name="タスク", subtask_name="サブ",
        estimated_time=10, actual_time=0, deadline_date_nearest="2025-01-01"
    )
    assert entry.attr_map("is_done") == "実行済"
    assert entry.attr_map("task_name") == "タスク名"
    assert entry.attr_map("unknown") == "unknown"
