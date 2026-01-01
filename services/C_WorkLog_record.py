import os
import sys
from datetime import datetime, timedelta

import pandas as pd

import models.Task_definition as Task_def

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 工数実績CSVのカラム定義
WORKLOG_COLUMNS = [
    "オーダ番号", "オーダ略称", "プロジェクト略称",
    "タスクID", "サブタスクID", "タスク名", "サブタスク名",
    "開始時刻", "終了時刻"
]

# -------------------------------------------------------------
# wordの各項と対応する関数
# -------------------------------------------------------------


def start_new_timer_and_record_WorkLog(
        willdo_date: str, timer_minutes: int,
        task_id: str, subtask_id: str) -> None:
    """2.3.1項 通常のタイマー時刻を工数実績csvとタスクcsvに記録し、タイマーを設定する関数

    Args:
        willdo_date (str): 呼び出し元のWillDoリストcsvの日付（YYMMDD形式）
        timer_minutes (int): 呼び出し元のタイマーの分数
        task_id (str): 呼び出し元のタスクID
        subtask_id (str): 呼び出し元のサブタスクID

    Raises:
        ValueError: サブタスクIDがタスクに存在しない場合
    """

    # 1. タスクidのタスクcsvを読み込み
    task_csv_path = _get_task_csv_path(task_id)
    task = Task_def.read_task_csv(task_csv_path)

    # 2. 読み込んだタスクcsvからオーダ番号、タスク名、サブタスクidに対応するサブタスク名、サブタスク実績時間を取得
    order_number = task.order_number
    task_name = task.name
    subtask_row = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id]
    if subtask_row.empty:
        raise ValueError(f"サブタスクID '{subtask_id}' がタスク '{task_id}' に見つかりません")
    subtask_name = subtask_row.iloc[0]["name"]
    subtask_actual_time = int(subtask_row.iloc[0]["actual_time"])

    # 3. オーダ管理csvを読み込んで、オーダ番号に対応するオーダ略称とプロジェクト略称を取得
    order_info = Task_def.OrderInformation()
    order_abbr = order_info.get_order_abbr(order_number)
    project_abbr = order_info.get_project_abbr(order_number)

    # 4. 開始時刻と終了時刻を算出
    # 4-1. 現在時刻を開始時刻とする
    start_time = datetime.now()
    # 4-2. 終了時刻は、開始時刻にtimer_minutesを加算したものとする
    end_time = start_time + timedelta(minutes=timer_minutes)

    # 時刻を 'YYYY-MM-DD HH:MM:SS' 形式の文字列に変換
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    # 5. 工数実績csvに記録
    # 5-1. willdo_dateに対応する工数実績csvが存在するか確認
    worklog_csv_path = _get_worklog_csv_path(willdo_date)

    # 5-2. 存在しない場合は新規作成
    if not os.path.exists(worklog_csv_path):
        _create_worklog_csv(worklog_csv_path)

    # 5-3. 工数実績csvに新しい行を追加
    worklog_df = pd.read_csv(worklog_csv_path, encoding="utf-8")
    new_row = pd.DataFrame([{
        WORKLOG_COLUMNS[0]: order_number,
        WORKLOG_COLUMNS[1]: order_abbr,
        WORKLOG_COLUMNS[2]: project_abbr,
        WORKLOG_COLUMNS[3]: task_id,
        WORKLOG_COLUMNS[4]: subtask_id,
        WORKLOG_COLUMNS[5]: task_name,
        WORKLOG_COLUMNS[6]: subtask_name,
        WORKLOG_COLUMNS[7]: start_time_str,
        WORKLOG_COLUMNS[8]: end_time_str
    }])
    worklog_df = pd.concat([worklog_df, new_row], ignore_index=True)

    # 5-4. csvを保存
    worklog_df.to_csv(worklog_csv_path, index=False, encoding="utf-8")

    # 6. タスクcsvにサブタスク実績時間を更新して保存
    # 6-1. サブタスク実績時間にtimer_minutesを加算
    new_actual_time = subtask_actual_time + timer_minutes

    # 6-2. サブタスク実績時間を更新してタスクcsvを保存
    subtask_index = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id].index[0]
    task.sub_tasks.at[subtask_index, "actual_time"] = new_actual_time
    task.save_to_csv()

    # 7. タイマー設定関数を呼び出し
    # ここは後回し、別ファイルの関数を呼び出す形で実装予定
    print(f"タイマー設定関数を呼び出します: {timer_minutes}分")

    return


def continuously_timer_and_record_WorkLog(
        willdo_date: str, task_id: str, subtask_id: str) -> None:
    """2.3.2項 継続タイマー時刻を工数実績csvとタスクcsvに記録する関数

    既存の実績最終行の終了時刻を現在時刻に更新し、
    入力されたタスクの新規行を追加する。

    Args:
        willdo_date (str): 呼び出し元のWillDoリストcsvの日付（YYMMDD形式）
        task_id (str): 呼び出し元のタスクID
        subtask_id (str): 呼び出し元のサブタスクID

    Raises:
        ValueError: 工数実績csvが存在しない場合
        ValueError: 工数実績csvに既存の実績行がない場合
        ValueError: サブタスクIDがタスクに存在しない場合
    """
    # 現在時刻を取得
    current_time = datetime.now()

    # 1. 工数実績csvの既存の実績最終行に対する処理
    # 1-1. 工数実績csvから既存の実績最終行のタスクid、サブタスクid、開始時刻、終了時刻を取得
    worklog_csv_path = _get_worklog_csv_path(willdo_date)
    if not os.path.exists(worklog_csv_path):
        raise ValueError(f"工数実績csv '{worklog_csv_path}' が存在しません")

    worklog_df = pd.read_csv(worklog_csv_path, encoding="utf-8")
    if worklog_df.empty:
        raise ValueError(f"工数実績csv '{worklog_csv_path}' に既存の実績行がありません")

    last_row = worklog_df.iloc[-1]
    last_task_id = last_row[WORKLOG_COLUMNS[3]]
    last_subtask_id = last_row[WORKLOG_COLUMNS[4]]
    last_start_time_str = last_row[WORKLOG_COLUMNS[7]]
    last_end_time_str = last_row[WORKLOG_COLUMNS[8]]

    # 時刻文字列をdatetimeオブジェクトに変換
    last_start_time = datetime.strptime(last_start_time_str, "%Y-%m-%d %H:%M:%S")
    last_end_time = datetime.strptime(last_end_time_str, "%Y-%m-%d %H:%M:%S")

    # 1-2. 既存の実績最終行のタスクcsvを更新
    # 1-2-1. 既存の実績最終行のタスクid、サブタスクidに一致するサブタスクを取得
    last_task_csv_path = _get_task_csv_path(last_task_id)
    last_task = Task_def.read_task_csv(last_task_csv_path)

    last_subtask_row = last_task.sub_tasks[last_task.sub_tasks["subtask_id"] == last_subtask_id]
    if last_subtask_row.empty:
        raise ValueError(f"サブタスクID '{last_subtask_id}' がタスク '{last_task_id}' に見つかりません")
    last_subtask_actual_time = int(last_subtask_row.iloc[0]["actual_time"])

    # 1-2-2. サブタスク実績時間を更新
    # ※更新後の実績時間 = 既存の実績時間 - (既存の終了時刻 - 既存の開始時刻) + (現在時刻 - 既存の開始時刻)
    old_duration_minutes = int((last_end_time - last_start_time).total_seconds() / 60)
    new_duration_minutes = int((current_time - last_start_time).total_seconds() / 60)
    last_subtask_new_actual_time = last_subtask_actual_time - old_duration_minutes + new_duration_minutes

    last_subtask_index = last_task.sub_tasks[last_task.sub_tasks["subtask_id"] == last_subtask_id].index[0]
    last_task.sub_tasks.at[last_subtask_index, "actual_time"] = last_subtask_new_actual_time
    last_task.save_to_csv()

    # 1-3. 工数実績csvの既存の実績最終行の終了時刻を現在時刻に更新して保存
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    worklog_df.at[worklog_df.index[-1], WORKLOG_COLUMNS[8]] = current_time_str
    worklog_df.to_csv(worklog_csv_path, index=False, encoding="utf-8")

    # 2. 入力されたタスク（新規の工数実績行）の追加処理
    # 2-1. 入力されたタスクidのタスクcsvを読み込み
    task_csv_path = _get_task_csv_path(task_id)
    task = Task_def.read_task_csv(task_csv_path)

    # 2-2. 入力されたcsvからオーダ番号、タスク名、サブタスクidに対応するサブタスク名、サブタスク実績時間を取得
    order_number = task.order_number
    task_name = task.name
    subtask_row = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id]
    if subtask_row.empty:
        raise ValueError(f"サブタスクID '{subtask_id}' がタスク '{task_id}' に見つかりません")
    subtask_name = subtask_row.iloc[0]["name"]
    subtask_actual_time = int(subtask_row.iloc[0]["actual_time"])

    # 2-3. オーダ管理csvを読み込んで、オーダ番号に対応するオーダ略称とプロジェクト略称を取得
    order_info = Task_def.OrderInformation()
    order_abbr = order_info.get_order_abbr(order_number)
    project_abbr = order_info.get_project_abbr(order_number)

    # 2-4. 入力されたタスクの開始時刻と終了時刻を算出
    # 2-4-1. 開始時刻は、現在時刻とする
    start_time = current_time
    # 2-4-2. 終了時刻は、既存の実績最終行の終了時刻（更新前の値）とする
    end_time = last_end_time
    # 2-4-3. 時刻を 'YYYY-MM-DD HH:MM:SS' 形式の文字列に変換
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    # 2-5. 工数実績csvの最終行に新しい行（入力されたタスクの内容）を追加して保存
    worklog_df = pd.read_csv(worklog_csv_path, encoding="utf-8")  # 更新後のcsvを再読み込み
    new_row = pd.DataFrame([{
        WORKLOG_COLUMNS[0]: order_number,
        WORKLOG_COLUMNS[1]: order_abbr,
        WORKLOG_COLUMNS[2]: project_abbr,
        WORKLOG_COLUMNS[3]: task_id,
        WORKLOG_COLUMNS[4]: subtask_id,
        WORKLOG_COLUMNS[5]: task_name,
        WORKLOG_COLUMNS[6]: subtask_name,
        WORKLOG_COLUMNS[7]: start_time_str,
        WORKLOG_COLUMNS[8]: end_time_str
    }])
    worklog_df = pd.concat([worklog_df, new_row], ignore_index=True)
    worklog_df.to_csv(worklog_csv_path, index=False, encoding="utf-8")

    # 2-6. 入力されたタスクのタスクcsvにサブタスク実績時間を更新して保存
    # ※更新後の実績時間 = 既存の実績時間 + (終了時刻 - 開始時刻)
    duration_minutes = int((end_time - start_time).total_seconds() / 60)
    new_actual_time = subtask_actual_time + duration_minutes

    subtask_index = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id].index[0]
    task.sub_tasks.at[subtask_index, "actual_time"] = new_actual_time
    task.save_to_csv()

    return


def check_WorkLog_latest_end_datetime(willdo_date: str) -> datetime:

    # 工数実績csvの最新の実績行を取得
    worklog_csv_path = _get_worklog_csv_path(willdo_date)

    if not os.path.exists(worklog_csv_path):
        raise ValueError(f"工数実績csv '{worklog_csv_path}' が存在しません")

    worklog_df = pd.read_csv(worklog_csv_path, encoding="utf-8")
    if worklog_df.empty:
        raise ValueError(f"工数実績csv '{worklog_csv_path}' に実績行がありません")

    last_row = worklog_df.iloc[-1]
    last_end_time_str = last_row[WORKLOG_COLUMNS[8]]
    last_end_time = datetime.strptime(last_end_time_str, "%Y-%m-%d %H:%M:%S")

    return last_end_time

# -------------------------------------------------------------
# 上記の関数で使用する補助関数群
# -------------------------------------------------------------

def _get_task_csv_path(task_id: str) -> str:
    """タスクIDからタスクCSVファイルのパスを構築する。

    Args:
        task_id (str): タスクID

    Returns:
        str: タスクCSVファイルのパス
    """
    if len(task_id) >= 6 and task_id[:6].isdigit():
        folder_path = os.path.join("data", "Project", "Active")
    else:
        folder_path = os.path.join("data", "Daily", "Active")
    return os.path.join(folder_path, f"{task_id}.csv")


def _get_worklog_csv_path(willdo_date: str) -> str:
    """willdo_dateから工数実績CSVファイルのパスを構築する。

    Args:
        willdo_date (str): WillDo日付（YYMMDD形式）

    Returns:
        str: 工数実績CSVファイルのパス
    """
    return os.path.join("data", "WorkLogs", f"工数実績{willdo_date}.csv")


def _create_worklog_csv(file_path: str) -> None:
    """空の工数実績CSVファイルを新規作成する。

    Args:
        file_path (str): 作成するファイルのパス
    """
    df = pd.DataFrame(columns=WORKLOG_COLUMNS)
    df.to_csv(file_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    pass