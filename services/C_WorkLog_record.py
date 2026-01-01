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


if __name__ == "__main__":
    pass