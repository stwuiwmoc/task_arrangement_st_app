import os
import sys
from datetime import datetime, timedelta

import pytest

# プロジェクトのルートパスを取得してPythonパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import models.Task_definition as Task_def
import services.B_WillDo_create as Output_B


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


def test_get_latest_work_log_date(tmp_path):
    worklog_dir = tmp_path / "data" / "WorkLogs"
    worklog_dir.mkdir(parents=True, exist_ok=True)
    file1 = worklog_dir / "工数実績240101.csv"
    file2 = worklog_dir / "工数実績251017.csv"
    file1.write_text("dummy1", encoding="utf-8")
    file2.write_text("dummy2", encoding="utf-8")
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        latest_date = Output_B.get_latest_WillDo_date()
        assert isinstance(latest_date, datetime)
        assert latest_date.strftime("%y%m%d") == "251017"
    finally:
        os.chdir(old_cwd)


def test_get_dates_since_date():
    base_date = datetime(2025, 10, 17)
    date_list = Output_B.get_dates_since_date(base_date - timedelta(days=2))
    assert date_list[0] == (base_date - timedelta(days=1)).date()
    assert date_list[-1] <= datetime.now().date()


def test_get_matched_Daily_Task_dict(csv_data_dir):
    # テスト用のディレクトリとファイルを作成
    daily_active_dir = os.path.join(csv_data_dir, "data", "Daily", "Active")
    os.makedirs(daily_active_dir, exist_ok=True)
    # 例: 25Day001.csv, 25Mon002.csv, 25M17003.csv
    csv_content = (
        "タスク名\n\nZZZ-1000\n\n\n\n\n\n\n\n"
        "#001,処理,15,0,,,True,True,0,False\n"
        "#002,処理251015,15,15,,,True,True,1,False\n"
    )
    with open(os.path.join(daily_active_dir, "25Day001.csv"), "w", encoding="utf-8") as f:
        f.write(csv_content)
    with open(os.path.join(daily_active_dir, "25Mon002.csv"), "w", encoding="utf-8") as f:
        f.write(csv_content)
    with open(os.path.join(daily_active_dir, "25M17003.csv"), "w", encoding="utf-8") as f:
        f.write(csv_content)

    # テスト対象の日付リストを作成
    base_date = datetime(2025, 10, 17)  # 金曜日
    monday_date = datetime(2025, 10, 13)  # 月曜日
    date_list = [base_date, monday_date]

    # カレントディレクトリをcsv_data_dirに変更
    old_cwd = os.getcwd()
    os.chdir(csv_data_dir)
    try:
        # 関数名修正
        tasks_dict = Output_B.get_matched_DailyTasks(date_list)
        # ファイル名の拡張子除去がキーになっていることを確認
        assert "25Day001" in tasks_dict
        assert "25Mon002" in tasks_dict
        assert "25M17003" in tasks_dict
        # サブタスク辞書でアクセスできること
        for task in tasks_dict.values():
            assert isinstance(task.sub_tasks, dict)
            assert "#001" in task.sub_tasks
            assert "#002" in task.sub_tasks
            assert isinstance(task.sub_tasks["#001"], Task_def.SubTask)
            assert isinstance(task.sub_tasks["#002"], Task_def.SubTask)
    finally:
        os.chdir(old_cwd)


def test_add_WillDo_Tasks(csv_data_dir):
    # テスト用のTaskとSubTaskを作成
    subtask1 = Task_def.SubTask(
        subtask_id="#001",
        name="サブタスク1",
        estimated_time=10,
        actual_time=0,
        is_initial=True,
        is_nominal=True,
        sort_index=0,
        is_incomplete=True,
        deadline_date=None,
        deadline_reason=None
    )
    subtask2 = Task_def.SubTask(
        subtask_id="#002",
        name="サブタスク2",
        estimated_time=20,
        actual_time=5,
        is_initial=False,
        is_nominal=False,
        sort_index=1,
        is_incomplete=False,
        deadline_date=None,
        deadline_reason=None
    )
    task = Task_def.Task(
        task_id="99Day001",
        name="テストタスク",
        order_number="TEST-ORDER",
        sub_tasks={"#001": subtask1, "#002": subtask2},
        waiting_date=None
    )
    tasks_dict = {"99Day001": task}
    import pandas as pd

    # 必要なディレクトリを作成し、Task CSVを書き出す
    daily_active_dir = os.path.join(csv_data_dir, "data", "Daily", "Active")
    os.makedirs(daily_active_dir, exist_ok=True)
    # --- ここから追加 ---
    order_dir = os.path.join(csv_data_dir, "data")
    os.makedirs(order_dir, exist_ok=True)
    order_csv_path = os.path.join(order_dir, "オーダ管理.csv")
    with open(order_csv_path, "w", encoding="utf-8") as f:
        f.write("TEST-ORDER,TEST-PJ,TEST-ORDER-ABBR,テストオーダ名\n")
    # --- ここまで追加 ---
    old_cwd = os.getcwd()
    os.chdir(csv_data_dir)
    try:
        task.save_to_csv()
        WillDo_df = pd.DataFrame(
            columns=[col.metadata["label"] for col in Task_def.WillDoEntry.__dataclass_fields__.values()])
        WillDo_df = Output_B.add_WillDo_Tasks(WillDo_df, tasks_dict)
        # サブタスク1のみ追加される（未完了かつsort_index最小）
        # print(WillDo_df)  # ← ここで中身を確認すると全てNaNになっているはず
        assert len(WillDo_df) == 1
        assert WillDo_df.iloc[0]["タスクID"] == "99Day001"
        assert WillDo_df.iloc[0]["サブID"] == "#001"
        assert WillDo_df.iloc[0]["サブ名"] == "サブタスク1"
    finally:
        os.chdir(old_cwd)


def test_Initialize_Daily_Tasks(tmp_path):
    # テスト用のTaskとSubTaskを作成し、#000を持つTaskを用意
    subtask0 = Task_def.SubTask(
        subtask_id="#000",
        name="ベースサブタスク",
        estimated_time=10,
        actual_time=0,
        is_initial=True,
        is_nominal=True,
        sort_index=0,
        is_incomplete=True,
        deadline_date=None,
        deadline_reason=None
    )
    task = Task_def.Task(
        task_id="99Day001",
        name="テストタスク",
        order_number="TEST-ORDER",
        sub_tasks={"#000": subtask0},
        waiting_date=None
    )
    tasks_dict = {"99Day001": task}
    # 保存先ディレクトリを作成
    daily_active_dir = tmp_path / "data" / "Daily" / "Active"
    daily_active_dir.mkdir(parents=True, exist_ok=True)
    # カレントディレクトリを一時的に変更
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Task.save_to_csv()が正常に動作することも確認
        # 関数名修正
        result_dict = Output_B.add_DailyTasks_today_SubTask(tasks_dict)
        # #000のコピーが追加されていることを確認
        assert "#001" in result_dict["99Day001"].sub_tasks
        assert result_dict["99Day001"].sub_tasks["#001"].name.startswith("ベースサブタスク")
    finally:
        os.chdir(old_cwd)


def test_create_new_WillDo_with_Daily_Tasks(tmp_path):
    # 必要なディレクトリ・ファイルを作成
    worklog_dir = tmp_path / "data" / "WorkLogs"
    worklog_dir.mkdir(parents=True, exist_ok=True)
    (worklog_dir / "工数実績251017.csv").write_text("dummy", encoding="utf-8")

    daily_active_dir = tmp_path / "data" / "Daily" / "Active"
    daily_active_dir.mkdir(parents=True, exist_ok=True)
    csv_content = (
        "タスク名\n\nZZZ-1000\n\n\n\n\n\n\n\n"
        "#000,サブタスク,10,0,,,True,True,0,True\n"
    )
    (daily_active_dir / "25Day001.csv").write_text(csv_content, encoding="utf-8")

    order_csv_path = tmp_path / "data" / "オーダ管理.csv"
    order_csv_path.write_text("ZZZ-1000,PJ,ORD,テスト\n", encoding="utf-8")

    willdo_dir = tmp_path / "data" / "WillDo"
    willdo_dir.mkdir(parents=True, exist_ok=True)

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Output_B.create_new_WillDo_with_DailyTasks()
        willdo_file = willdo_dir / f"WillDo{datetime.now().strftime('%y%m%d')}.csv"
        assert willdo_file.exists()
        import pandas as pd
        df = pd.read_csv(willdo_file, encoding="utf-8-sig")
        assert not df.empty
        assert "タスクID" in df.columns
        assert df.iloc[0]["タスクID"] == "25Day001"
        assert "サブ名" in df.columns
        assert df.iloc[0]["サブ名"].startswith("サブタスク")
    finally:
        os.chdir(old_cwd)


def test_add_WillDo_all_ProjectTasks(tmp_path):
    # Project/ActiveディレクトリとタスクCSV作成
    project_active_dir = tmp_path / "data" / "Project" / "Active"
    project_active_dir.mkdir(parents=True, exist_ok=True)
    csv_content = (
        "タスク名\n\nTEST-ORDER\n\n\n\n\n\n\n\n"
        "#001,サブタスクP,5,0,,,True,True,0,True\n"
    )
    (project_active_dir / "990001.csv").write_text(csv_content, encoding="utf-8")

    order_csv_path = tmp_path / "data" / "オーダ管理.csv"
    order_csv_path.write_text("TEST-ORDER,PJ,ORD,テスト\n", encoding="utf-8")

    willdo_dir = tmp_path / "data" / "WillDo"
    willdo_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    WillDo_df = pd.DataFrame(
        columns=[col.metadata["label"] for col in Task_def.WillDoEntry.__dataclass_fields__.values()])
    willdo_file = willdo_dir / f"WillDo{datetime.now().strftime('%y%m%d')}.csv"
    WillDo_df.to_csv(willdo_file, index=False, encoding="utf-8-sig")

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Output_B.add_WillDo_all_ProjectTasks()
        # dtype=str を追加
        import pandas as pd
        df = pd.read_csv(willdo_file, encoding="utf-8-sig", dtype=str)
        assert not df.empty
        assert "タスクID" in df.columns
        assert df.iloc[0]["タスクID"] == "990001"
        assert df.iloc[0]["サブ名"].startswith("サブタスクP")
    finally:
        os.chdir(old_cwd)
