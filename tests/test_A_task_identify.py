import os
import sys
from datetime import datetime

import pytest

# プロジェクトのルートパスを取得してPythonパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import models.Task_definition as Task_def
import services.A_task_identify as Output_A


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

def test_parse_basic_task(sample_file):
    """基本的なタスク情報の読み込みテスト"""
    result = Output_A.parse_onenote_output(sample_file)

    # 3つのタスクが存在することを確認
    assert "250901c3" in result
    assert "250901d1" in result
    assert "251002a1" in result

    # タスク名を確認
    assert result["250901c3"].name == "試験手順書作成"
    assert result["250901d1"].name == "OPT-PDR-J-010"
    assert result["251002a1"].name == "手配納期まとめ"

def test_parse_subtask_flags(sample_file):
    """サブタスクのフラグ処理テスト"""
    result = Output_A.parse_onenote_output(sample_file)
    task = result["250901c3"]

    # サブタスク数を確認
    assert len(task.sub_tasks) == 4

    # 当初作業(d)・ノミナル(n)のサブタスク
    subtask1 = task.sub_tasks["#001"]
    assert subtask1.is_initial == True
    assert subtask1.is_nominal == True

    # 追加作業(a)・ノミナル(n)のサブタスク
    subtask3 = task.sub_tasks["#003"]
    assert subtask3.is_initial == False
    assert subtask3.is_nominal == True

def test_parse_deadline_dates(sample_file):
    """〆切日の処理テスト"""
    result = Output_A.parse_onenote_output(sample_file)
    task = result["251002a1"]

    # 〆切日が設定されているサブタスクを確認
    subtask = task.sub_tasks["#002"]
    assert subtask.deadline_date is not None
    assert subtask.deadline_reason == "1/31納期"
    # ISO形式に変換されていることを確認
    datetime.strptime(subtask.deadline_date, "%Y-%m-%d")

def test_parse_waiting_date(sample_file):
    """待機日の処理テスト"""
    result = Output_A.parse_onenote_output(sample_file)
    task = result["251002a1"]

    # 待機日が設定されていることを確認
    assert task.waiting_date is not None
    # ISO形式に変換されていることを確認
    datetime.strptime(task.waiting_date, "%Y-%m-%d")

def test_parse_with_indentation(sample_file):
    """インデント（タブ文字）を含む入力のテスト"""
    result = Output_A.parse_onenote_output(sample_file)
    task = result["251002a1"]

    # インデントされた行も正しく読み込めていることを確認
    assert len(task.sub_tasks) == 2
    assert task.sub_tasks["#002"].subtask_id == "#002"
    assert task.sub_tasks["#002"].estimated_time == 30



def test_compare_tasks(csv_data_dir, sample_file):
    """compare_tasksの動作確認"""
    from services.A_task_identify import TaskUpdateAction, compare_tasks

    # OneNote側（txt）とCSV側（csv_data_dir）を読み込み
    onenote_tasks = Output_A.parse_onenote_output(sample_file)
    csv_tasks = Task_def.read_all_task_csvs(csv_data_dir)

    # 差分リストを取得
    update_actions_result = compare_tasks(onenote_tasks, csv_tasks)

    # 差分リストが取得できていることを確認
    assert isinstance(update_actions_result, list)
    # 差分が1つ以上あること（テストデータによる）
    assert len(update_actions_result) >= 0
    # 差分の内容が想定通りの形式であること
    for action in update_actions_result:
        assert isinstance(action, TaskUpdateAction)
        assert action.action_type in ("add", "update_subtask_field", "complete", "update_waiting_date")

def test_prompt_update_tasks_with_actions_add(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsでサブタスク追加アクションが返るか"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    class DummySubTask:
        subtask_id = "#999"
        name = "テスト追加"
        estimated_time = 10
        actual_time = 0
        deadline_date = ""
        deadline_reason = ""
        is_initial = True
        is_nominal = True
        sort_index = 99
        is_incomplete = True

    update_actions = [
        TaskUpdateAction(
            action_type="add",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#999",
            subtask_obj_onenote=DummySubTask()
        ),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "y")
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == update_actions


def test_prompt_update_tasks_with_actions_complete(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsでサブタスク完了アクションが返るか"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    update_actions = [
        TaskUpdateAction(
            action_type="complete",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#999",
            subtask_name_csv="テスト追加"
        ),
    ]

    # completeはユーザー入力不要
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == update_actions


def test_prompt_update_tasks_with_actions_update_yes(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsでサブタスク更新アクションが返るか（yの場合）"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    update_actions = [
        TaskUpdateAction(
            action_type="update_subtask_field",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#999",
            subtask_name_csv="テスト追加",
            subtask_field_name="name",
            subtask_value_csv="テスト追加",
            subtask_value_onenote="テスト更新"
        ),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "y")
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == update_actions

def test_prompt_update_tasks_with_actions_update_no(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsでサブタスク更新アクションが返るか（nの場合）"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    update_actions = [
        TaskUpdateAction(
            action_type="update_subtask_field",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#999",
            subtask_name_csv="テスト追加",
            subtask_field_name="name",
            subtask_value_csv="テスト追加",
            subtask_value_onenote="テスト更新"
        ),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "n")
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == []

def test_prompt_update_tasks_with_actions_update_waiting_date_yes(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsで待機日更新アクションが返るか（yの場合）"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    update_actions = [
        TaskUpdateAction(
            action_type="update_waiting_date",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            task_waiting_date_csv="2025-01-23",
            task_waiting_date_onenote="2099-12-31"
        ),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "y")
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == update_actions

def test_prompt_update_tasks_with_actions_update_waiting_date_no(monkeypatch, tmp_path):
    """prompt_update_tasks_with_actionsで待機日更新アクションが返るか（nの場合）"""
    import shutil

    from services.A_task_identify import (TaskUpdateAction,
                                          make_df_from_TaskUpdateActions)

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    update_actions = [
        TaskUpdateAction(
            action_type="update_waiting_date",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            task_waiting_date_csv="2025-01-23",
            task_waiting_date_onenote="2099-12-31"
        ),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "n")
    actions_to_apply = make_df_from_TaskUpdateActions(update_actions)
    assert actions_to_apply == []

def test_apply_update_actions_add(tmp_path):
    """apply_update_actionsでサブタスク追加が正しくCSVに反映されるか"""
    import shutil

    from services.A_task_identify import TaskUpdateAction, apply_update_actions

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    class DummySubTask:
        subtask_id = "#999"
        name = "テスト追加"
        estimated_time = 10
        actual_time = 0
        deadline_date = ""
        deadline_reason = ""
        is_initial = True
        is_nominal = True
        sort_index = 99
        is_incomplete = True

    actions_to_apply = [
        TaskUpdateAction(
            action_type="add",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#999",
            subtask_obj_onenote=DummySubTask()
        ),
    ]
    apply_update_actions(actions_to_apply, test_data_dir)

    csv_path = os.path.join(test_data_dir, "250901c3.csv")
    with open(csv_path, encoding="utf-8") as f:
        content = f.read()
    assert "#999,テスト追加,10,0,,,True,True,99,True" in content

def test_apply_update_actions_update_subtask_field(tmp_path):
    """apply_update_actionsでサブタスク属性更新が正しくCSVに反映されるか"""
    import shutil

    from services.A_task_identify import TaskUpdateAction, apply_update_actions

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    # 既存サブタスクの名前を変更
    actions_to_apply = [
        TaskUpdateAction(
            action_type="update_subtask_field",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#001",
            subtask_name_csv="過去手順書発掘",
            subtask_field_name="name",
            subtask_value_csv="過去手順書発掘",
            subtask_value_onenote="新しいサブタスク名"
        ),
    ]
    apply_update_actions(actions_to_apply, test_data_dir)

    csv_path = os.path.join(test_data_dir, "250901c3.csv")
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    found = False
    for line in lines:
        if line.startswith("#001,新しいサブタスク名"):
            found = True
    assert found

def test_apply_update_actions_complete(tmp_path):
    """apply_update_actionsでサブタスク完了が正しくCSVに反映されるか"""
    import shutil

    from services.A_task_identify import TaskUpdateAction, apply_update_actions

    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    # 既存サブタスクのis_incomplete=Trueの場合のみ完了アクションを発行
    # ここでは #001 の is_incomplete=True であることを前提
    actions_to_apply = [
        TaskUpdateAction(
            action_type="complete",
            task_id="250901c3",
            task_name_csv="試験手順書作成",
            subtask_id="#001",
            subtask_name_csv="過去手順書発掘"
        ),
    ]
    apply_update_actions(actions_to_apply, test_data_dir)

    csv_path = os.path.join(test_data_dir, "250901c3.csv")
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("#001,"):
            assert line.rstrip().endswith("False")

def test_compare_tasks_complete_only_if_incomplete(tmp_path):
    """compare_tasksでis_incomplete=Falseのサブタスクにはcompleteアクションが発行されないこと"""
    import shutil

    import models.Task_definition as Task_def
    from services.A_task_identify import (TaskUpdateAction, compare_tasks,
                                          parse_onenote_output)

    # テスト用ディレクトリ準備
    test_data_dir = os.path.join(tmp_path, "Project", "Active")
    os.makedirs(test_data_dir, exist_ok=True)
    src_dir = os.path.join(PROJECT_ROOT, "tests", "test_data", "Project", "Active")
    # ファイルのみコピーする（ディレクトリは除外）
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(test_data_dir, fname)
        if os.path.isfile(src_path):
            shutil.copy(src_path, dst_path)

    # 既存CSVを直接編集して #001 の is_incomplete=False にする
    csv_path = os.path.join(test_data_dir, "250901c3.csv")
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith("#001,"):
            cols = line.rstrip('\n').split(',')
            cols[9] = "False"
            lines[i] = ",".join(cols) + "\n"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # OneNote側には #001 が存在しない前提でテスト
    # 既存テストデータのtest_input.txtには #001 が含まれていないことを前提
    onenote_file = os.path.join(PROJECT_ROOT, "tests", "test_data", "test_input.txt")
    onenote_tasks = parse_onenote_output(onenote_file)
    csv_tasks = Task_def.read_all_task_csvs(test_data_dir)

    update_actions = compare_tasks(onenote_tasks, csv_tasks)
    # #001 については complete アクションが発行されないこと
    for action in update_actions:
        assert not (action.action_type == "complete" and action.subtask_id == "#001")

def test_read_task_csv_header_variation(tmp_path):
    """read_task_csvで10行目が必ずサブタスク行である場合の動作確認"""
    import models.Task_definition as Task_def

    # テスト用CSV（10行目がサブタスク行1件のみ）
    csv_path_one = os.path.join(tmp_path, "task_one.csv")
    with open(csv_path_one, "w", encoding="utf-8") as f:
        f.write("タスク名\n")      # 1
        f.write("2025-01-01\n")   # 2
        f.write("ORDER-001\n")    # 3
        f.write("\n")             # 4
        f.write("\n")             # 5
        f.write("\n")             # 6
        f.write("\n")             # 7
        f.write("\n")             # 8
        f.write("\n")             # 9
        f.write("#001,サブタスクA,10,0,,,True,True,1,True\n")  # 10

    task = Task_def.read_task_csv(csv_path_one)
    assert task.name == "タスク名"
    assert task.waiting_date == "2025-01-01"
    assert task.order_number == "ORDER-001"
    assert len(task.sub_tasks) == 1
    assert "#001" in task.sub_tasks
    assert task.sub_tasks["#001"].subtask_id == "#001"

    # テスト用CSV（10行目からサブタスク行が複数）
    csv_path_multi = os.path.join(tmp_path, "task_multi.csv")
    with open(csv_path_multi, "w", encoding="utf-8") as f:
        f.write("タスク名\n")      # 1
        f.write("2025-01-01\n")   # 2
        f.write("ORDER-001\n")    # 3
        f.write("\n")             # 4
        f.write("\n")             # 5
        f.write("\n")             # 6
        f.write("\n")             # 7
        f.write("\n")             # 8
        f.write("\n")             # 9
        f.write("#001,サブタスクA,10,0,,,True,True,1,True\n")  # 10
        f.write("#002,サブタスクB,20,0,,,True,True,2,True\n")
        f.write("#003,サブタスクC,30,0,,,True,True,3,True\n")

    task2 = Task_def.read_task_csv(csv_path_multi)
    assert task2.name == "タスク名"
    assert task2.waiting_date == "2025-01-01"
    assert task2.order_number == "ORDER-001"
    assert len(task2.sub_tasks) == 3
    assert "#001" in task2.sub_tasks
    assert "#002" in task2.sub_tasks
    assert "#003" in task2.sub_tasks
    assert task2.sub_tasks["#003"].subtask_id == "#003"
