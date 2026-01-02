import os
import sys
from datetime import datetime, timedelta

import pandas as pd

import models.Task_definition as Task_def
import services.D_external_timer_boot as Output_D

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
    # 1. 開始時刻と終了時刻を算出
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=int(timer_minutes))

    # 2. 工数実績csvの既存の実績最終行に対する処理
    _update_last_worklog_row_if_overlap(willdo_date, start_time)

    # 3. 入力されたタスク情報を取得
    task_info = _get_task_info_for_worklog(task_id, subtask_id)

    # 4. 工数実績csvに新しい行を追加
    _add_worklog_row(
        willdo_date=willdo_date,
        order_number=task_info["order_number"],
        order_abbr=task_info["order_abbr"],
        project_abbr=task_info["project_abbr"],
        task_id=task_id,
        subtask_id=subtask_id,
        task_name=task_info["task_name"],
        subtask_name=task_info["subtask_name"],
        start_time=start_time,
        end_time=end_time
    )

    # 5. タスクcsvにサブタスク実績時間を更新して保存
    _update_subtask_actual_time(
        task_id=task_id,
        subtask_id=subtask_id,
        additional_minutes=int(timer_minutes)
    )

    # 6. タイマー設定関数を呼び出し
    Output_D.send_timer_boot_email(timer_minutes)

    return


def continuously_start_and_record_WorkLog(
        willdo_date: str, task_id: str, subtask_id: str) -> None:
    """2.3.2項 「続けて開始」した時にタスクcsvと工数実績csvの上書き・追加を行う関数

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
    # 1. 開始時刻（現在時刻）を取得
    current_time = datetime.now()

    # 2. 既存の最終行の終了時刻（更新前）を取得
    # ※check_WorkLog_latest_end_datetime内で存在確認・空チェックも行われる
    last_end_time = check_WorkLog_latest_end_datetime(willdo_date)

    # 3. 工数実績csvの既存の実績最終行に対する処理（overlapがあれば更新）
    _update_last_worklog_row_if_overlap(willdo_date, current_time)

    # 3. 入力されたタスク情報を取得
    task_info = _get_task_info_for_worklog(task_id, subtask_id)

    # 4. 工数実績csvに新しい行を追加
    # 終了時刻は既存の実績最終行の終了時刻（更新前の値）を引き継ぐ
    start_time = current_time
    end_time = last_end_time

    _add_worklog_row(
        willdo_date=willdo_date,
        order_number=task_info["order_number"],
        order_abbr=task_info["order_abbr"],
        project_abbr=task_info["project_abbr"],
        task_id=task_id,
        subtask_id=subtask_id,
        task_name=task_info["task_name"],
        subtask_name=task_info["subtask_name"],
        start_time=start_time,
        end_time=end_time
    )

    # 5. 入力されたタスクのタスクcsvにサブタスク実績時間を更新して保存
    duration_minutes = int((end_time - start_time).total_seconds() / 60)
    _update_subtask_actual_time(
        task_id=task_id,
        subtask_id=subtask_id,
        additional_minutes=duration_minutes
    )

    return


def record_completed_meeting_WorkLog(
        willdo_date: str, achievement_minutes: int,
        meeting_name: str, order_number: str
        ) -> None:
    """2.3.3項 終了済み打合せの工数実績を記録する関数

    Args:
        willdo_date (str): 呼び出し元のWillDoリストcsvの日付（YYMMDD形式）
        achievement_minutes (int): 会議の実績時間（分）
        meeting_name (str): 会議名（タスク名として記録）
        order_number (str): オーダ番号
    """
    # 1. 開始時刻と終了時刻を算出
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=int(achievement_minutes))

    # 2. タスクidを 'MTG-HHMM' 形式で作成
    task_id = f"MTG-{start_time.strftime('%H%M')}"

    # 3. 工数実績csvの既存の実績最終行に対する処理
    _update_last_worklog_row_if_overlap(willdo_date, start_time)

    # 4. オーダ情報を取得
    order_info = Task_def.OrderInformation()
    order_abbr = order_info.get_order_abbr(order_number)
    project_abbr = order_info.get_project_abbr(order_number)

    # 5. 工数実績csvに新しい行を追加
    _add_worklog_row(
        willdo_date=willdo_date,
        order_number=order_number,
        order_abbr=order_abbr,
        project_abbr=project_abbr,
        task_id=task_id,
        subtask_id="#000",
        task_name=meeting_name,
        subtask_name="",
        start_time=start_time,
        end_time=end_time
    )

    # ※打合せはタスクcsvが存在しないため、サブタスク実績時間の更新は不要

    return


def record_completed_task_WorkLog(
        willdo_date: str, achievement_minutes: int,
        task_id: str, subtask_id: str,
        ) -> None:
    """2.3.3項 終了済みタスクの工数実績を記録する関数

    Args:
        willdo_date (str): 呼び出し元のWillDoリストcsvの日付（YYMMDD形式）
        achievement_minutes (int): タスクの実績時間（分）
        task_id (str): タスクID
        subtask_id (str): サブタスクID
    """
    # 1. 開始時刻と終了時刻を算出
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=int(achievement_minutes))

    # 2. 工数実績csvの既存の実績最終行に対する処理
    _update_last_worklog_row_if_overlap(willdo_date, start_time)

    # 3. 入力されたタスク情報を取得
    task_info = _get_task_info_for_worklog(task_id, subtask_id)

    # 4. 工数実績csvに新しい行を追加
    _add_worklog_row(
        willdo_date=willdo_date,
        order_number=task_info["order_number"],
        order_abbr=task_info["order_abbr"],
        project_abbr=task_info["project_abbr"],
        task_id=task_id,
        subtask_id=subtask_id,
        task_name=task_info["task_name"],
        subtask_name=task_info["subtask_name"],
        start_time=start_time,
        end_time=end_time
    )

    # 5. 入力されたタスクのタスクcsvにサブタスク実績時間を更新して保存
    _update_subtask_actual_time(
        task_id=task_id,
        subtask_id=subtask_id,
        additional_minutes=int(achievement_minutes)
    )

    return

def check_WorkLog_latest_end_datetime(willdo_date: str) -> datetime:
    """工数実績csvの最終行の終了時刻をdatetime型で取得する

    Args:
        willdo_date (str): 呼び出し元のWillDoリストcsvの日付（YYMMDD形式）

    Raises:
        ValueError: 工数実績csvが存在しない場合
        ValueError: 工数実績csvに実績行がない場合

    Returns:
        datetime: 工数実績csvの最終行の終了時刻のdatetimeオブジェクト
    """

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


def _get_task_info_for_worklog(task_id: str, subtask_id: str) -> dict:
    """タスクID・サブタスクIDから工数実績記録に必要な情報を取得する。

    Args:
        task_id (str): タスクID
        subtask_id (str): サブタスクID

    Returns:
        dict: 以下のキーを持つ辞書
            - order_number: オーダ番号
            - order_abbr: オーダ略称
            - project_abbr: プロジェクト略称
            - task_name: タスク名
            - subtask_name: サブタスク名

    Raises:
        ValueError: サブタスクIDがタスクに存在しない場合
    """
    # タスクcsvを読み込み
    task_csv_path = _get_task_csv_path(task_id)
    task = Task_def.read_task_csv(task_csv_path)

    # タスク情報を取得
    order_number = task.order_number
    task_name = task.name

    # サブタスク情報を取得
    subtask_row = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id]
    if subtask_row.empty:
        raise ValueError(f"サブタスクID '{subtask_id}' がタスク '{task_id}' に見つかりません")
    subtask_name = subtask_row.iloc[0]["name"]

    # オーダ情報を取得
    order_info = Task_def.OrderInformation()
    order_abbr = order_info.get_order_abbr(order_number)
    project_abbr = order_info.get_project_abbr(order_number)

    return {
        "order_number": order_number,
        "order_abbr": order_abbr,
        "project_abbr": project_abbr,
        "task_name": task_name,
        "subtask_name": subtask_name
    }


def _update_last_worklog_row_if_overlap(
        willdo_date: str, new_start_time: datetime) -> None:
    """新タスクの開始時刻が既存最終行の終了時刻より前の場合、工数実績csv既存最終行とその行に対応するタスクcsvを更新する。

    新タスクの開始時刻が既存最終行の終了時刻以降の場合は何もしない。
    工数実績csvが存在しない、または空の場合も何もしない。

    Args:
        willdo_date (str): WillDo日付（YYMMDD形式）
        new_start_time (datetime): 新タスクの開始時刻
    """
    worklog_csv_path = _get_worklog_csv_path(willdo_date)

    # 工数実績csvが存在しない、または空の場合は何もしない
    try:
        last_end_time = check_WorkLog_latest_end_datetime(willdo_date)
    except ValueError:
        return

    # 開始時刻が最終行の終了時刻以降の場合は何もしない
    if new_start_time >= last_end_time:
        return

    # 開始時刻が最終行の終了時刻より前の場合、既存最終行を更新
    worklog_df = pd.read_csv(worklog_csv_path, encoding="utf-8")
    last_row = worklog_df.iloc[-1]
    last_task_id = last_row[WORKLOG_COLUMNS[3]]
    last_subtask_id = last_row[WORKLOG_COLUMNS[4]]
    last_start_time_str = last_row[WORKLOG_COLUMNS[7]]
    last_start_time = datetime.strptime(last_start_time_str, "%Y-%m-%d %H:%M:%S")

    # 既存の実績最終行のタスクcsvを更新
    last_task_csv_path = _get_task_csv_path(last_task_id)
    if os.path.exists(last_task_csv_path):
        last_task = Task_def.read_task_csv(last_task_csv_path)
        last_subtask_row = last_task.sub_tasks[last_task.sub_tasks["subtask_id"] == last_subtask_id]

        if not last_subtask_row.empty:
            last_subtask_actual_time = int(last_subtask_row.iloc[0]["actual_time"])

            # サブタスク実績時間を更新
            # ※更新後の実績時間 = 既存の実績時間 - (既存の終了時刻 - 既存の開始時刻) + (新タスク開始時刻 - 既存の開始時刻)
            old_duration_minutes = int((last_end_time - last_start_time).total_seconds() / 60)
            new_duration_minutes = int((new_start_time - last_start_time).total_seconds() / 60)
            last_subtask_new_actual_time = last_subtask_actual_time - old_duration_minutes + new_duration_minutes

            last_subtask_index = last_task.sub_tasks[last_task.sub_tasks["subtask_id"] == last_subtask_id].index[0]
            last_task.sub_tasks.at[last_subtask_index, "actual_time"] = last_subtask_new_actual_time
            last_task.save_to_csv()

    # 工数実績csvの既存の実績最終行の終了時刻を新タスク開始時刻に更新して保存
    new_start_time_str = new_start_time.strftime("%Y-%m-%d %H:%M:%S")
    worklog_df.at[worklog_df.index[-1], WORKLOG_COLUMNS[8]] = new_start_time_str
    worklog_df.to_csv(worklog_csv_path, index=False, encoding="utf-8")


def _add_worklog_row(
        willdo_date: str,
        order_number: str, order_abbr: str, project_abbr: str,
        task_id: str, subtask_id: str,
        task_name: str, subtask_name: str,
        start_time: datetime, end_time: datetime) -> None:
    """工数実績csvに新しい行を追加する。

    工数実績csvが存在しない場合は新規作成する。

    Args:
        willdo_date (str): WillDo日付（YYMMDD形式）
        order_number (str): オーダ番号
        order_abbr (str): オーダ略称
        project_abbr (str): プロジェクト略称
        task_id (str): タスクID
        subtask_id (str): サブタスクID
        task_name (str): タスク名
        subtask_name (str): サブタスク名
        start_time (datetime): 開始時刻
        end_time (datetime): 終了時刻
    """
    worklog_csv_path = _get_worklog_csv_path(willdo_date)

    # 存在しない場合は新規作成
    if not os.path.exists(worklog_csv_path):
        _create_worklog_csv(worklog_csv_path)

    # 時刻を 'YYYY-MM-DD HH:MM:SS' 形式の文字列に変換
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    # 工数実績csvに新しい行を追加
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
    worklog_df.to_csv(worklog_csv_path, index=False, encoding="utf-8")


def _update_subtask_actual_time(
        task_id: str, subtask_id: str, additional_minutes: int) -> None:
    """タスクcsvのサブタスク実績時間を更新して保存する。

    Args:
        task_id (str): タスクID
        subtask_id (str): サブタスクID
        additional_minutes (int): 加算する実績時間（分）

    Raises:
        ValueError: サブタスクIDがタスクに存在しない場合
    """
    task_csv_path = _get_task_csv_path(task_id)
    task = Task_def.read_task_csv(task_csv_path)

    subtask_row = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id]
    if subtask_row.empty:
        raise ValueError(f"サブタスクID '{subtask_id}' がタスク '{task_id}' に見つかりません")

    subtask_actual_time = int(subtask_row.iloc[0]["actual_time"])
    new_actual_time = subtask_actual_time + additional_minutes

    subtask_index = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id].index[0]
    task.sub_tasks.at[subtask_index, "actual_time"] = new_actual_time
    task.save_to_csv()


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