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
import services.E_WorkLog_formatting as Output_E

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
        # base_dateなしの場合、end_dateを本日を含む月の最終日に設定する
        next_month_first = base_date.replace(day=1) + timedelta(days=32)
        end_date = next_month_first.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(seconds=1)
    else:
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
        # #000を除いたサブタスクを基準に処理する
        non_000_df = task.sub_tasks[task.sub_tasks["subtask_id"] != "#000"]
        is_000_only = non_000_df.empty

        incomplete_df = non_000_df[non_000_df["is_incomplete"] == True]

        # #000を除いた見込み時間合計
        estimated_total = non_000_df["estimated_time"].sum()

        # 完了済実績合計: #000のみの場合は完了済サブタスクなしとして扱う
        if is_000_only:
            actual_completed_total = 0
        else:
            actual_completed_total = non_000_df[non_000_df["is_incomplete"] == False]["actual_time"].sum()

        # 残時間算出（未完了サブタスクの見込み時間合計）
        estimated_remaining = incomplete_df["estimated_time"].sum()

        # 補正後残り時間算出（完了済サブタスクの実績と見込みの乖離に応じて補正）
        estimated_remaining_corrected = calculate_remaining_estimated_time(task_id)

        # 補正後合計時間算出
        estimated_total_corrected = actual_completed_total + estimated_remaining_corrected

        # 進捗率算出
        progress = (estimated_total - estimated_remaining_corrected) / estimated_total * 100 if estimated_total > 0 else 0

        # 直近〆切算出（未完了サブタスクをサブタスク順序でソートし、最初の〆切日を取得）
        incomplete_df_sorted = incomplete_df.sort_values(by="sort_index")
        next_deadline = None
        for d in incomplete_df_sorted["deadline_date"]:
            d_date = _parse_date_str(d)
            if d_date is not None:
                next_deadline = d_date
                break

        # 未完了サブタスク数: #000のみの場合は#000も計上する
        incomplete_count = (
            len(task.sub_tasks[task.sub_tasks["is_incomplete"] == True])
            if is_000_only
            else len(incomplete_df)
        )

        summary_data.append({
            "タスクID": task_id,
            "タスク名": task.name,
            "PJ略": order_info.get_project_abbr(task.order_number),
            "オーダ略": order_info.get_order_abbr(task.order_number),
            "状態": _classify_task_status(task, today),
            "見込み残り": estimated_remaining,
            "補正後残り": estimated_remaining_corrected,
            "完了済実績合計": actual_completed_total,
            "見込み合計": estimated_total,
            "補正後合計": estimated_total_corrected,
            "進捗率(%)": round(progress, 0),
            "未完了サブタスク数": incomplete_count,
            "直近〆切": next_deadline.strftime("%Y-%m-%d") if next_deadline is not None else None,
            "待機日": task.waiting_date if task.waiting_date is not None else None,
        })
    return pd.DataFrame(summary_data)


def calculate_remaining_estimated_time(task_ID: str) -> int:
    """タスクオブジェクト内の残見込み時間の合計を、完了済サブタスクの実績と見込みの乖離を考慮して計算する
    サブID "#000" は除外して計算するが、サブID #000 しかない場合は、#000 の見込み時間を残見込み時間として返す

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

    # サブタスクID "#000" は除外して処理する
    sub_tasks = task.sub_tasks[task.sub_tasks["subtask_id"] != "#000"]

    # "#000" 以外のサブタスクが存在しない場合は、"#000" の見込み時間をそのまま返す
    if sub_tasks.empty:
        row_000 = task.sub_tasks[task.sub_tasks["subtask_id"] == "#000"]
        return int(row_000["estimated_time"].sum())

    # タスク全体の見込み時間合計を算出する
    estimated_total = sub_tasks["estimated_time"].sum()

    # 未完了サブタスクの見込み時間合計を算出する
    incomplete_df = sub_tasks[sub_tasks["is_incomplete"] == True]
    estimated_incomplete = incomplete_df["estimated_time"].sum()

    # 完了済サブタスクの見込み時間合計を算出する（着手の有無に関わらず）
    complete_df = sub_tasks[sub_tasks["is_incomplete"] == False]
    estimated_complete = complete_df["estimated_time"].sum()

    # 完了済サブタスクの見込み時間 / タスク全体の見込み時間 の比率を算出する
    ratio_complete_weight = estimated_complete / estimated_total

    # 着手済かつ完了済のサブタスクのみを抽出
    execute_complete_df = complete_df[complete_df["actual_time"] > 0]

    # もし着手済の完了済サブタスクが存在しない場合は、補正値算出のための情報が無いので補正計算のしようが無い
    # 補正は行わずに未完了サブタスクの見込み時間合計をそのまま返す
    if execute_complete_df.empty:
        return int(estimated_incomplete)

    # 着手済かつ完了済サブタスクの見込み時間合計を算出する
    estimated_execute_complete = execute_complete_df["estimated_time"].sum()

    # 完了済サブタスクの実績時間合計を算出する
    actual_complete = execute_complete_df["actual_time"].sum()

    # 着手済かつ完了済サブタスクの実績時間 / 着手済かつ完了済サブタスクの見込み時間 の比率を算出し
    # 1を引くことで、実績が見込みよりどれだけ乖離しているかを表す比率を算出する
    # （0で見込み通り、正で実績が見込みより多い、負で実績が見込みより少ない）
    ratio_pace = (actual_complete / estimated_execute_complete) - 1

    # 比率同士を掛け算する（0で見込み通り、正で実績が見込みより多い、負で実績が見込みより少ない）
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
    """タスクの状態を[段取り中,〆切未定,〆切超過,完了間近,〆切迫る,未着手,着手済]に分類する

    Args:
        task (Task_def.Task): Taskオブジェクト
        today (datetime.date): 今日の日付
        urgent_days (int, optional): 緊急とみなす日数。デフォルトは2日。

    Returns:
        str: タスクの状態を表す文字列
    """
    # #000を除いたサブタスク・未完了サブタスクを基準に分類する
    non_000_df = task.sub_tasks[task.sub_tasks["subtask_id"] != "#000"]
    incomplete_df = non_000_df[non_000_df["is_incomplete"] == True]

    # 段取り中（サブタスクが#000のみで、かつそのサブタスクが未完了の場合）
    if non_000_df.empty and task.sub_tasks["is_incomplete"].any():
        return "段取り中"

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

    # 未着手（#000を除いたサブタスク実績時間合計が0）
    if non_000_df["actual_time"].sum() == 0:
        return "未着手"

    return "着手済"  # 上記どれにも該当しない場合は単に着手済とみなす


# -------------------------------------------------------------
# 工数実績集約(ダッシュボード3-A用)
# -------------------------------------------------------------

def load_worklogs_in_period(start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """指定期間の全工数実績csvを結合し、作業区分の列を追加

    Args:
        start_date (datetime): 開始日
        end_date (datetime): 終了日

    Returns:
        pd.DataFrame: 指定期間の工数実績csvを結合したDataFrame
    """

    all_files = []
    for folder in ["data/WorkLogs", "data/WorkLogs/old"]:
        if os.path.exists(folder):
            all_files.extend(glob.glob(os.path.join(folder, "工数実績*.csv")))

    dfs = []
    for path in all_files:
        fname = os.path.basename(path)
        try:
            date_str = fname.replace("工数実績", "").replace(".csv", "")
            file_date = datetime.strptime(date_str, "%y%m%d").date()

        except ValueError:
            continue  # ファイル名が想定外の形式の場合はスキップ

        if not (start_date.date() <= file_date <= end_date.date()):
            continue  # 指定期間外のファイルはスキップ

        # try:
        # ZZZ-1050（工数切り捨て分調整）の算出処理
        # オーダ番号列がZZZ-1050の行が存在する場合は工数を取得し、存在しない場合は0を設定
        other = "ZZZ-1050"

        df_sum_by_order = Output_E.sum_df_each_order(
            Output_E.sum_df_each_subtask(
                path, include_MTG=True))
        other_work_time = df_sum_by_order.loc[df_sum_by_order["オーダ番号"] == other, "工数"].sum()

        # 結合用の工数実績csvの読み込み
        df = pd.read_csv(path, parse_dates=["開始時刻", "終了時刻"])
        df["ファイル日付"] = file_date

        # dfの先頭行に工数切り捨て分調整の行を追加する
        if other_work_time > 0:
            # 開始時刻は5:00、終了時刻は5:00 + 工数切り捨て分調整の時間（分）を設定する
            other_start_time = pd.Timestamp.combine(file_date, pd.Timestamp("05:00").time())
            other_end_time = other_start_time + pd.to_timedelta(other_work_time, unit="m")

            new_row = {
                "オーダ番号": other,
                "オーダ略称": Task_def.OrderInformation().get_order_abbr(other),
                "プロジェクト略称": Task_def.OrderInformation().get_project_abbr(other),
                "タスクID": "ZZZ1050",
                "サブタスクID": "#000",
                "タスク名": "工数切り捨て分調整",
                "サブタスク名": "",
                "開始時刻": other_start_time,
                "終了時刻": other_end_time,
                "ファイル日付": file_date,
            }
            df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)

            dfs.append(df)

        # except Exception:
        #     continue  # CSV読み込みに失敗した場合はスキップ

    if not dfs:
        return pd.DataFrame()  # データがない場合は空のDataFrameを返す

    combined = pd.concat(dfs, ignore_index=True)
    combined["開始時刻"] = pd.to_datetime(combined["開始時刻"].dt.floor("min"))
    combined["終了時刻"] = pd.to_datetime(combined["終了時刻"].dt.floor("min"))
    combined["作業時間(分)"] = (
        (combined["終了時刻"] - combined["開始時刻"]).dt.total_seconds() / 60
    ).astype(int)

    # 作業区分判定：タスクIDが"MTG"で始まるものを会議、"DSC"で始まるものを議論、それ以外を作業とする
    combined["区分"] = combined["タスクID"].apply(
        lambda x: "会議" if str(x).startswith("MTG") else ("議論" if str(x).startswith("DSC") else "作業"))

    combined["年月"] = pd.to_datetime(combined["ファイル日付"]).dt.strftime("%Y-%m")

    return combined


def aggregate_monthly_by_order(
        worklog_df: pd.DataFrame, include_mtg: bool = True, include_dsc: bool = True
        ) -> pd.DataFrame:
    """月×オーダ略×区分での工数集計

    Args:
        worklog_df (pd.DataFrame): 工数実績のDataFrame
        include_mtg (bool, optional): 会議を含めるかどうか。デフォルトはTrue。
        include_dsc (bool, optional): 議論を含めるかどうか。デフォルトはTrue。

    Returns:
        pd.DataFrame: 月×オーダ略×区分で集計したDataFrame
    """

    if worklog_df.empty:
        return pd.DataFrame()

    df = worklog_df.copy()
    if not include_mtg:
        df = df[df["区分"] != "会議"]
    if not include_dsc:
        df = df[df["区分"] != "議論"]
    grouped = df.groupby(["年月", "オーダ略称", "区分"])["作業時間(分)"].sum().reset_index()
    grouped["作業時間(h)"] = (grouped["作業時間(分)"] / 60).round(1)

    return grouped


def get_order_sort_df() -> pd.DataFrame:
    """オーダ管理CSVを結合・ソートしたオーダ情報DataFrameを返す

    並び順: 「間接」PJ略を最後に、その他はPJ略→オーダ略称の昇順。
    重複するオーダ略称はオーダ管理.csvを優先する。

    Returns:
        pd.DataFrame: ["PJ略", "オーダ略称"] の列を持つDataFrame
    """
    old_csv = os.path.join("data", "オーダ管理_old.csv")
    df_new = Task_def.OrderInformation().df
    df_old = (
        Task_def.OrderInformation(csv_path=old_csv).df
        if os.path.exists(old_csv)
        else pd.DataFrame(columns=df_new.columns)
    )

    combined = pd.concat([df_new, df_old], ignore_index=True).drop_duplicates(
        subset=["order_abbr"], keep="first"
    )
    combined["_is_indirect"] = combined["project_abbr"] == "間接"
    combined = combined.sort_values(
        ["_is_indirect", "project_abbr", "order_abbr"]
    ).drop(columns=["_is_indirect"])

    return combined[["project_abbr", "order_abbr"]].rename(
        columns={"project_abbr": "PJ略", "order_abbr": "オーダ略称"}
    ).reset_index(drop=True)


def get_order_abbr_sort_order() -> list[str]:
    """オーダ略称の順序リストを返す（get_order_sort_dfに委譲）

    Returns:
        list[str]: オーダ略称の順序リスト
    """
    return get_order_sort_df()["オーダ略称"].tolist()