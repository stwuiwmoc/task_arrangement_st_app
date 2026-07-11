"""
ダッシュボード用の横断集計モジュール
既存のE_WorkLog_formatting.py（1日単位の集計）と役割分担し、
本モジュールは「複数日の結合」「全Activeタスク横断」を担当する
"""
import glob
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def

# -------------------------------------------------------------
# 期間フィルタ
# -------------------------------------------------------------

def get_period_range(
        period_key: str, base_date: Optional[datetime] = None,
    ) -> tuple[datetime, datetime]:
    """期間キー（1M, 3M, 6M, 1Y）から期間の開始日と終了日を返す

    Args:
        period_key (str): 期間キー（1M, 3M, 6M, 1Y）
        base_date (Optional[datetime], optional): 基準日。指定しない場合は現在日時を使用。 Defaults to None.

    Returns:
        tuple[datetime, datetime]: 期間の開始日と終了日
    """

    if base_date is None:
        base_date = Task_def.get_ESS_dt()

    end_date = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    delta_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    start_date = end_date - timedelta(days=delta_map.get(period_key, 30))
    return start_date, end_date

# -------------------------------------------------------------
# Activeタスクの横断集計(ダッシュボード1-A用)
# -------------------------------------------------------------

def build_active_task_summary_df() -> pd.DataFrame:
    """全Activeタスクの横断集計を行い、DataFrameとして返す

    Returns:
        pd.DataFrame: タスクID, タスク名, 状態, 総見込み時間, 総実績時間, サブタスク数, 未完了サブタスク数を含むDataFrame
    """
    tasks = _collect_all_active_tasks()
    today = Task_def.get_ESS_dt().date()
    order_info = Task_def.OrderInformation()

    summary_data = []
    for task_id, task in tasks.items():
        incomplete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]

        estimated_total = task.sub_tasks["estimated_time"].sum()
        actual_total = task.sub_tasks["actual_time"].sum()

        # 残時間算出（未完了サブタスクの見込み時間合計）
        estimated_remaining = incomplete_df["estimated_time"].sum()

        # 補正後残り時間算出（完了済サブタスクの実績と見込みの乖離に応じて補正）
        estimated_remaining_corrected = calculate_remaining_estimated_time(task_id)

        # 補正後合計時間算出
        estimated_total_corrected = actual_total + estimated_remaining_corrected

        # 進捗率算出
        progress = (estimated_total - estimated_remaining) / estimated_total * 100 if estimated_total > 0 else 0

        # 直近〆切算出（未完了サブタスクをサブタスク順序でソートし、最初の〆切日を取得）
        incomplete_df_sorted = incomplete_df.sort_values(by="sort_index")
        next_deadline = None
        for d in incomplete_df_sorted["deadline_date"]:
            d_date = _parse_date_str(d)
            if d_date is not None:
                next_deadline = d_date
                break

        summary_data.append({
            "タスクID": task_id,
            "タスク名": task.name,
            "PJ略": order_info.get_project_abbr(task.order_number),
            "オーダ略": order_info.get_order_abbr(task.order_number),
            "状態": _classify_task_status(task, today),
            "見込み残り": estimated_remaining,
            "補正後残り": estimated_remaining_corrected,
            "実績合計": actual_total,
            "見込み合計": estimated_total,
            "補正後合計": estimated_total_corrected,
            "進捗率(%)": round(progress, 0),
            "未完了サブタスク数": len(incomplete_df),
            "直近〆切": next_deadline.strftime("%Y-%m-%d") if next_deadline is not None else None,
            "待機日": task.waiting_date if task.waiting_date is not None else None,
        })
    return pd.DataFrame(summary_data)


def calculate_remaining_estimated_time(task_ID: str) -> int:
    """タスクオブジェクト内の残見込み時間の合計を、完了済サブタスクの実績と見込みの乖離を考慮して計算する

    Args:
        task_ID (str): アクティブ状態のプロジェクトタスクまたはデイリータスクのタスクID

    Returns:
        int: 残見込み時間の合計（分単位）
    """
    # タスクIDに対応するタスクオブジェクトを取得する
    # タスクIDの冒頭6文字がすべて数字ならProject/Active、そうでなければDaily/Active
    if len(task_ID) >= 6 and task_ID[:6].isdigit():
        folder_path = os.path.join("data", "Project", "Active")
    else:
        folder_path = os.path.join("data", "Daily", "Active")

    # タスクとサブタスクを取得
    task = Task_def.read_task_csv(os.path.join(folder_path, f"{task_ID}.csv"))
    if task is None:
        raise ValueError(f"タスクID '{task_ID}' が見つかりません")

    # タスク全体の見込み時間合計を算出する
    estimated_total = task.sub_tasks["estimated_time"].sum()

    # 未完了サブタスクの見込み時間合計を算出する
    incomplete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]
    estimated_incomplete = incomplete_df["estimated_time"].sum()

    # 完了済サブタスクの見込み時間合計を算出する（着手の有無に関わらず）
    complete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == False]
    estimated_complete = complete_df["estimated_time"].sum()

    # 完了済サブタスクの見込み時間 / タスク全体の見込み時間 の比率を算出する
    ratio_complete_weight = estimated_complete / estimated_total
    print(f"ID: {task_ID}, estimated_total: {estimated_total}, estimated_incomplete: {estimated_incomplete}, estimated_complete: {estimated_complete}, ratio_complete_weight: {ratio_complete_weight}")

    # 着手済かつ完了済のサブタスクのみを抽出
    execute_complete_df = complete_df[complete_df["actual_time"] > 0]

    # もし着手済の完了済サブタスクが存在しない場合は、ratio_paceを1とする
    if execute_complete_df.empty:
        return int(estimated_incomplete * ratio_complete_weight)

    # 着手済かつ完了済サブタスクの見込み時間合計を算出する
    estimated_execute_complete = execute_complete_df["estimated_time"].sum()

    # 完了済サブタスクの実績時間合計を算出する
    complete_actual = execute_complete_df["actual_time"].sum()

    # 着手済かつ完了済サブタスクの実績時間 / 着手済かつ完了済サブタスクの見込み時間 の比率を算出し
    # 1を引くことで、実績が見込みよりどれだけ乖離しているかを表す比率を算出する
    # （0で見込み通り、正で実績が見込みより多い、負で実績が見込みより少ない）
    ratio_pace = complete_actual / estimated_execute_complete - 1
    print(f"ID: {task_ID}, complete_actual: {complete_actual}, complete_estimated: {estimated_execute_complete}, ratio_pace: {ratio_pace}")

    # 比率同士を掛け算する
    combined_ratio = ratio_complete_weight * ratio_pace

    # 掛け算の結果を、未完了サブタスクの見込み時間合計に掛け算する
    # これにより、完了済サブタスクの実績と見込みの乖離を考慮した残見込み時間の合計が算出される
    return int(estimated_incomplete * (1 + combined_ratio))


def _collect_all_active_tasks() -> dict[str, Task_def.Task]:
    """Project/ActiveとDaily/Activeの全タスクをまとめて読み込む

    Returns:
        dict[str, Task_def.Task]: タスクIDをキー、Taskオブジェクトを値とする辞書
    """
    tasks = {}
    for folder in [
        "data/Project/Active",
        # "data/Daily/Active"
        ]:
        if os.path.exists(folder):
            tasks.update(Task_def.read_all_task_csvs(folder))
    return tasks


def _parse_date_str(s) -> Optional[datetime.date]:
    """Task csvの日付文字列をdatetime.dateに変換する。変換できない場合はNoneを返す

    Args:
        s (str): 文字列

    Returns:
        Optional[datetime.date]: 変換後の日付オブジェクト。変換できない場合はNone
    """
    if s is None or pd.isna(s) or str(s).strip() == "":
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except ValueError:
        return None


def _classify_task_status(
        task: Task_def.Task,
        today: datetime.date,
        urgent_days: int = 2) -> str:
    """タスクの状態を[〆切未定,〆切超過,完了間近,〆切迫る,未着手,着手済]に分類する

    Args:
        task (Task_def.Task): Taskオブジェクト
        today (datetime.date): 今日の日付
        urgent_days (int, optional): 緊急とみなす日数。デフォルトは2日。

    Returns:
        str: タスクの状態を表す文字列
    """
    incomplete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]

    # 〆切未定（未完了サブタスクのすべてで〆切未設定）
    if incomplete_df["deadline_date"].apply(_parse_date_str).isna().all():
        return "〆切未定"

    # 〆切超過（未完了サブタスクのいずれかで〆切超過）
    for d in incomplete_df["deadline_date"]:
        d_date = _parse_date_str(d)
        if d_date is not None and (d_date - today).days < 0:
            return "〆切超過"

    # 完了間近（未完了サブタスクの補正込み見込み時間合計が一定時間以内）
    threshold_minute = 45  # 完了間近とみなす見込み時間の閾値（時間）
    estimated_remaining_corrected = calculate_remaining_estimated_time(task.task_id)
    if estimated_remaining_corrected <= threshold_minute:
        return "完了間近"

    # 〆切迫る（未完了にurgent_days以内の〆切がある）
    for d in incomplete_df["deadline_date"]:
        d_date = _parse_date_str(d)
        if d_date is not None and 0 <= (d_date - today).days <= urgent_days:
            return "〆切迫る"

    # 未着手（サブタスク実績時間合計が0）
    if incomplete_df["actual_time"].sum() == 0:
        return "未着手"

    return "着手済"  # 上記どれにも該当しない場合は単に着手済とみなす
