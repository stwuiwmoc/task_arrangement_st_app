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

        # 残時間算出（後で改善）
        remaining = estimated_total - actual_total

        # 進捗率算出（後で改善）
        progress = actual_total / estimated_total * 100 if estimated_total > 0 else 0

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
            "残見込み(分)": remaining,
            "総見込み(分)": estimated_total,
            "実績合計(分)": actual_total,
            "進捗率(%)": round(progress, 2),
            "未完了サブタスク数": len(incomplete_df),
            "直近〆切": next_deadline.strftime("%Y-%m-%d") if next_deadline is not None else None,
            "待機日": task.waiting_date if task.waiting_date is not None else None,
        })
    return pd.DataFrame(summary_data)


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
    """タスクの状態を[待機中,〆切未定,〆切超過,完了間近,〆切迫る,未着手,着手済]に分類する

    Args:
        task (Task_def.Task): Taskオブジェクト
        today (datetime.date): 今日の日付
        urgent_days (int, optional): 緊急とみなす日数。デフォルトは2日。

    Returns:
        str: タスクの状態を表す文字列
    """
    incomplete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]

    # 待機中（待機日あり）
    w_date = _parse_date_str(task.waiting_date)
    if w_date is not None:
        return "待機中"

    # 〆切未定（未完了サブタスクのすべてで〆切未設定）
    if incomplete_df["deadline_date"].apply(_parse_date_str).isna().all():
        return "〆切未定"

    # 〆切超過（未完了サブタスクのいずれかで〆切超過）
    for d in incomplete_df["deadline_date"]:
        d_date = _parse_date_str(d)
        if d_date is not None and (d_date - today).days < 0:
            return "〆切超過"

    # 完了間近（未完了サブタスクの見込み時間合計が一定時間以内）
    threshold_minute = 30  # 完了間近とみなす見込み時間の閾値（時間）
    if incomplete_df["estimated_time"].sum() <= threshold_minute:
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
