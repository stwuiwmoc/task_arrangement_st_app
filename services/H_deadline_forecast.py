"""
〆切予測・負荷按分モジュール

G_dashboard_aggregation.py（過去実績の横断集計）と役割分担し、
本モジュールは「未来方向の予測」を担当する
"""
import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

import jpholiday
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.G_dashboard_aggregation as Output_G

# 所定労働時間（h/日）
BASE_WORK_HOUR = 7.75

# 日次負荷の種別
KIND_ALLOCATED = "按分"
KIND_OVERDUE = "〆切超過"
KIND_DAILY = "デイリー固定"

# 〆切超過・デイリー固定レイヤの固定色
COLOR_OVERDUE = "#F44336"
COLOR_DAILY = "#9e9e9e"

# -------------------------------------------------------------
# 共通ヘルパー（営業日計算・配色）
# -------------------------------------------------------------
def is_business_day(target_date: date) -> bool:
    """指定日が営業日（土日祝を除く平日）かどうかを判定する

    Args:
        target_date (date): 判定対象の日付

    Returns:
        bool: 指定日が営業日であればTrue、そうでなければFalse
    """
    if target_date.weekday() >= 5:
        return False
    if jpholiday.is_holiday(target_date):
        return False
    return True


def get_business_days(start_date: date, end_date: date) -> list[date]:
    """開始日から終了日までの営業日リストを返す（両端を含む）

    Args:
        start_date (date): 期間の開始日
        end_date (date): 期間の終了日

    Returns:
        list[date]: 営業日のリスト start_date > end_date の場合は空リストを返す
    """
    business_days = []
    d = start_date
    while d <= end_date:
        if is_business_day(d):
            business_days.append(d)
        d += timedelta(days=1)
    return business_days


def count_business_days(start_date: date, end_date: date) -> int:
    """開始日から終了日までの営業日数を返す（両端を含む）

    Args:
        start_date (date): 期間の開始日
        end_date (date): 期間の終了日

    Returns:
        int: 営業日数 start_date > end_date の場合は0を返す
    """
    return len(get_business_days(start_date, end_date))


def generate_order_colors(label_list: list[str]) -> dict[str, str]:
    """黄金比を使ってラベルごとに色相が均等分散した色を生成する

    Dashboard3_history.pyの_generate_order_colorsと同一ロジック
    ダッシュボード間で配色を統一するため本モジュールに公開関数として配置

    Args:
        label_list (list[str]): 色を割り当てるラベルのリスト

    Returns:
        dict[str, str]: ラベルをキー、16進数カラーコードを値とする辞書
    """
    import colorsys
    golden_ratio_conjugate = 0.618033988749895
    result={}
    for i, label in enumerate(label_list):
        hue = (i * golden_ratio_conjugate) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.50, 0.65)
        result[label] = "#{:02x}{:02x}{:02x}".format(int(r*255), int(g*255), int(b*255))
    return result

# -------------------------------------------------------------
# 〆切ブロックの構築
# -------------------------------------------------------------
def build_deadline_blocks_df(today: Optional[date] = None)-> pd.DataFrame:
    """Activeプロジェクトタスクの未完了サブタスクを「〆切ブロック」に分割する
    ブロックとは、サブタスク順序の昇順に未完了サブタスクを走し、
    〆切日を持つサブタスクで区切った単位のこと。
    〆切日を持たないサブタスクは、後続の最も近い〆切日に紐づけられる。

    例)001(30分,2/1〆) #002(90分、〆切なし) #003(60分,2/15〆) #004(45分、〆切なし)
    →ブロック1:〆切2/1 見込み 30分
    →ブロック2 〆切 2/15, 見込み 150分 (#002 #003)
    →ブロック3:〆切 None, 見込み 45分 (〆切未定のため負荷按分の対象外)

    Args:
        today (Optional[date], optional): B, RECESSE

    Returns:
        pd.DataFrame: DataFrame
    """
    if today is None:
        today = Task_def.get_ESS_dt().date()

    tasks = Output_G._collect_all_active_tasks()
    order_info = Task_def.OrderInformation()

    block_rows = []
    for task_id, task in tasks.items():
        # #000を除いた未完了サブタスクをサブタスク序の昇順で取得する
        non_000_df = task.sub_tasks[task.sub_tasks["subtask_id"] != "#000"]
        incomplete_df = non_000_df[non_000_df["is_incomplete"] == True].sort_values("sort_index")

        # 補正係数を算出する(完了済サブタスクの実績見込み乖離をブロックに按分するため)
        estimated_remaining = incomplete_df["estimated_time"].sum()
        corrected_remaining = Output_G.calculate_remaining_estimated_time(task_id)
        if estimated_remaining > 0:
            correction_ratio = corrected_remaining / estimated_remaining
        else:
            correction_ratio = 1.0
        # 待機日を取得する
        waiting_date = Output_G._parse_date_str(task.waiting_date)

        # タスク共通の属性をまとめる
        common_attr = {
            "タスクID": task_id,
            "タスク名": task.name,
            "PJ略": order_info.get_project_abbr(task.order_number),
            "オーダ略": order_info.get_order_abbr(task.order_number),
            "待機日": waiting_date,
            "状態": Output_G._classify_task_status(task, today)
        }

        # #000以外の未完了サブタスクが存在しない場合（段取り中）
        if incomplete_df.empty:
            row_000 = task.sub_tasks[
                (task.sub_tasks["subtask_id"] == "#000")
                & (task.sub_tasks["is_incomplete"] == True)
            ]
            if not row_000.empty:
                block_rows.append({
                    **common_attr,
                    "ブロック番号": 1,
                    "〆切": None,
                    "〆切サブID": "#000",
                    "〆切サブ名": row_000.iloc[0]["name"],
                    "〆切理由": row_000.iloc[0]["deadline_reason"],
                    "先頭サブID": "#000",
                    "先頭サブ名": row_000.iloc[0]["name"],
                    "構成サブ数": 1,
                    "見込み残り(分)": int(row_000.iloc[0]["estimated_time"]),
                    "補正後残り(分)": int(corrected_remaining),
                })
            continue

        # 未完了サブタスクを順に操作し、〆切日を持つサブタスクでブロックを閉じる
        block_index = 0
        buffer_rows = []
        for _, subtask in incomplete_df.iterrows():
            buffer_rows.append(subtask)
            deadline = Output_G._parse_date_str(subtask["deadline_date"])
            if deadline is None:
                continue
            block_index += 1
            block_estimated = sum(int(r["estimated_time"]) for r in buffer_rows)
            block_rows.append({
                **common_attr,
                "ブロック番号": block_index,
                "〆切": deadline,
                "〆切サブID": subtask["subtask_id"],
                "〆切サブ名": subtask["name"],
                "〆切理由": subtask["deadline_reason"],
                "先頭サブID": buffer_rows[0]["subtask_id"],
                "先頭サブ名": buffer_rows[0]["name"],
                "構成サブ数": len(buffer_rows),
                "見込み残り(分)": block_estimated,
                "補正後残り(分)": int(block_estimated * correction_ratio),
            })
            buffer_rows = []

        # 〆切日を持たないまま末尾に残ったサブタスクは〆切未定ブロックとする
        if buffer_rows:
            block_index += 1
            block_estimated = sum(int(r["estimated_time"]) for r in buffer_rows)
            block_rows.append({
                **common_attr,
                "ブロック番号": block_index,
                "〆切": None,
                "〆切サブID": None,
                "〆切サブ名": None,
                "〆切理由": None,
                "先頭サブID": buffer_rows[0]["subtask_id"],
                "先頭サブ名": buffer_rows[0]["name"],
                "構成サブ数": len(buffer_rows),
                "見込み残り(分)": block_estimated,
                "補正後残り(分)": int(block_estimated * correction_ratio),
            })
    blocks_df = pd.DataFrame(block_rows)
    if blocks_df.empty:
        return blocks_df

    # 按分の開始日を算出する
    blocks_df = _assign_block_start_dates(blocks_df, today)
    return blocks_df


def _assign_block_start_dates(blocks_df: pd.DataFrame, today: date) -> pd.DataFrame:
    """各〆切ブロックの按分開始日を算出して列に追加する

    開始日は「本日」「待機日」「同一タスクの前ブロックの〆切日」の最大値とする

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのdataframe
        today (date): 基準日

    Returns:
        pd.DataFrame: 「開始日」列を追加したDataFrame
    """
    start_dates = []
    for task_id, task_group in blocks_df.groupby("タスクID", sort=False):
        previous_deadline = None
        for idx, row in task_group.sort_values("ブロック番号").iterrows():
            candidates = [today]
            if row["待機日"] is not None:
                candidates.append(row["待機日"])
            if previous_deadline is not None:
                candidates.append(previous_deadline)
            start_dates.append((idx, max(candidates)))
            if row["〆切"] is not None:
                previous_deadline = row["〆切"]

    start_series = pd.Series(dict(start_dates))
    blocks_df = blocks_df.copy()
    blocks_df["開始日"] = blocks_df.index.map(start_series)
    return blocks_df


# ------------------------------------------------------------------------------
# 稼働可能時間の算出
# ------------------------------------------------------------------------------
def estimate_meeting_deduction_minutes(lookback_days: int = 30) -> float:
    """直近の工数実績から、1営業日あたりの会議・議論の平均時間を算出する

    Args:
        lookback_days (int, optional): 遡る日数。デフォルトは30日

    Returns:
        float: 1営業日あたりの会議・議論の平均時間(分)
    """
    end_date = Task_def.get_ESS_dt()
    start_date = end_date - timedelta(days=lookback_days)
    worklog_df = Output_G.load_worklogs_in_period(start_date, end_date)
    if worklog_df.empty:
        return 0.0

    meeting_df = worklog_df[worklog_df["区分"].isin(["会議", "議論"])]
    day_count = worklog_df["ファイル日付"].nunique()
    if day_count == 0:
        return 0.0

    return float(meeting_df["作業時間(分)"].sum() / day_count)


def build_capacity_df(
    start_date: date,
    end_date: date,
    overtime_hour: float = 0.0,
    meeting_deduction_minutes: float = 0.0,
    ) -> pd.DataFrame:
    """日次の稼働可能時間のDataFrameを作成する

    稼働可能時間=(所定7.75h+残業設定h)*60-会議控除分
    土日祝は0分とする。

    Args:
        start_date (date): 開始日
        end_date (date): 終了日
        overtime_hour (float, optional): 1日あたりの想定残業時間(h)
        meeting_deduction_minutes (float, optional): 1日あたりの会議控除時間(分)

    Returns:
        pd.DataFrame: 日付, 稼働可能(分)の列を持つDataFrame
    """
    records = []
    d = start_date
    while d <= end_date:
        if is_business_day(d):
            capacity = (BASE_WORK_HOUR + overtime_hour) * 60 - meeting_deduction_minutes
            capacity = max(0.0, capacity)
        else:
            capacity = 0.0

        records.append({"日付": d, "稼働可能(分)": capacity})
        d += timedelta(days=1)

    return pd.DataFrame(records)


def get_daily_capacity_minutes(
    target_date: date,
    overtime_hour: float = 0.0,
    meeting_deduction_minutes: float = 0.0,
    ) -> float:
    """指定日の稼働可能時間(分)を返す

    将来Outlookのicsカレンダー連携を実装する際は、本関数を差し替えることで対応する。

    Args:
        target_date (date): 対象日
        overtime_hour (float, optional): 1日あたりの想定残業時間 (h)
        meeting_deduction_minutes (float, optional): 1日あたりの会議控除時間(分)

    Returns:
        float: 稼働可能時間(分)
    """
    if not is_business_day(target_date):
        return 0.0

    return max(0.0, (BASE_WORK_HOUR + overtime_hour) * 60 - meeting_deduction_minutes)


# ------------------------------------------------------------------------------
# 日次負荷の算出
# ------------------------------------------------------------------------------
def calculate_daily_load(
    blocks_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    today: Optional[date] = None,
    ) -> pd.DataFrame:
    """〆切ブロックを営業日で均等按分し、日次負荷のDataFrameを作成する

    〆切超過のブロックは按分せず、本日に全量を計上する。
    〆切未定のブロックは按分対象外とする。

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのDataFrame
        start_date (date): 表示期間の開始日
        end_date (date): 表示期間の終了日
        today (Optional[date], optional): 基準日。指定しない場合はESS基準の本日

    Returns:
        pd.DataFrame: 日付・レイヤ・種別・負荷(分)の列を持つDataFrame
    """
    if today is None:
        today = Task_def.get_ESS_dt().date()

    if blocks_df.empty:
        return pd.DataFrame(columns=["日付", "レイヤ", "種別", "負荷(分)", "タスクID"])

    records = []
    for _, block in blocks_df.iterrows():
        deadline = block["〆切"]

        # 〆切未定ブロックは按分対象外
        if deadline is None:
            continue

        corrected_minutes = float(block["補正後残り(分)"])
        if corrected_minutes <= 0:
            continue

        # 〆切超過ブロックは本日に全量を計上する
        if deadline < today:
            if start_date <= today <= end_date:
                records.append({
                    "日付": today,
                    "レイヤ": KIND_OVERDUE,
                    "種別": KIND_OVERDUE,
                    "負荷(分)": corrected_minutes,
                    "タスクID": block["タスクID"],
                })
            continue

        # 按分対象の営業日を取得する
        block_start = max(block["開始日"], today)
        business_days = get_business_days(block_start, deadline)

        if not business_days:
            # 開始日から〆切日までに営業日が無い場合は〆切日に全量を計上する
            business_days = [deadline]

        minutes_per_day = corrected_minutes / len(business_days)

        for d in business_days:
            if not (start_date <= d <= end_date):
                continue
            records.append({
                "日付": d,
                "レイヤ": block["PJ略"] if block["PJ略"] else "未分類",
                "種別": KIND_ALLOCATED,
                "負荷(分)": minutes_per_day,
                "タスクID": block["タスクID"],
            })

    return pd.DataFrame(records)


def build_daily_fixed_load(start_date: date, end_date: date) -> pd.DataFrame:
    """デイリータスクの固定日次負荷のDataFrameを作成する

    デイリータスクは毎朝サブタスクが生成される運用のため未来に展開できない。
    そのためサブタスクID #000の見込み時間を、
    ファイル名の頻度識別子(Day/曜日3文字/Mdd) に従って各営業日に割り当てる。

    Args:
        start_date (date): 開始日
        end_date (date): 終了日

    Returns:
        pd.DataFrame: 日付・レイヤ・種別・負荷(分)の列を持つDataFrame
    """
    daily_active_dir = os.path.join("data", "Daily", "Active")
    if not os.path.exists(daily_active_dir):
        return pd.DataFrame(columns=["日付", "レイヤ", "種別", "負荷(分)", "タスクID"])

    # 各デイリータスクの頻度識別子と#000見込み時間を取得する
    daily_entries = []
    for fname in os.listdir(daily_active_dir):
        if not fname.endswith(".csv") or len(fname) < 9:
            continue
        try:
            task = Task_def.read_task_csv(os.path.join(daily_active_dir, fname))
        except Exception:
            continue

        row_000 = task.sub_tasks[task.sub_tasks["subtask_id"] == "#000"]
        if row_000.empty:
            continue

        daily_entries.append({
            "識別子": fname[2:5],
            "タスクID": task.task_id,
            "見込み": int(row_000.iloc[0]["estimated_time"]),
        })

    # 各営業日に対して該当するデイリータスクの見込み時間を合算する
    records = []
    d = start_date
    while d <= end_date:
        if is_business_day(d):
            day_of_week = d.strftime("%a").capitalize()
            day_of_month = f"M{d.day:02d}"
            for entry in daily_entries:
                if entry["識別子"] in ("Day", day_of_week, day_of_month):
                    records.append({
                        "日付": d,
                        "レイヤ": KIND_DAILY,
                        "種別": KIND_DAILY,
                        "負荷(分)": float(entry["見込み"]),
                        "タスクID": entry["タスクID"],
                    })
        d += timedelta(days=1)

    return pd.DataFrame(records)


def build_whatif_blocks_df(whatif_items: list[dict], today: Optional[date] = None) -> pd.DataFrame:
    """What-if入力から仮想の〆切ブロック DataFrameを作成する

    calculate_daily_load に実ブロックと結合して渡すことで、
    按分ロジックを二重実装せずにWhat-ifの負荷を算出できる。

    Args:
        whatif_items (list[dict]): 名称・見込み(分)・〆切・開始日を持つ辞書のリスト
        today (Optional[date], optional): 基準日。指定しない場合はESS基準の本日

    Returns:
        pd.DataFrame: 〆切ブロックと同じ列構成のDataFrame
    """
    if today is None:
        today = Task_def.get_ESS_dt().date()

    if not whatif_items:
        return pd.DataFrame()

    rows = []
    for i, item in enumerate(whatif_items, start=1):
        rows.append({
            "タスクID": f"WHATIF{i:02d}",
            "タスク名": item["名称"],
            "PJ略": "What-if",
            "オーダ略": "What-if",
            "オーダ番号": "",
            "待機日": None,
            "状態": "What-if",
            "ブロック番号": 1,
            "〆切": item["〆切"],
            "〆切サブID": "#001",
            "〆切サブ名": item["名称"],
            "〆切理由": "What-if想定",
            "先頭サブID": "#001",
            "先頭サブ名": item["名称"],
            "構成サブ数": 1,
            "見込み残り(分)": int(item["見込み(分)"]),
            "補正後残り(分)": int(item["見込み(分)"]),
            "開始日": max(today, item["開始日"]),
        })

    return pd.DataFrame(rows)


def summarize_daily_total(
    load_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
) -> pd.DataFrame:
    """日次負荷を合算し、稼働可能時間と比較したDataFrameを作成する

    Args:
        load_df (pd.DataFrame): 日次負荷のDataFrame
        capacity_df (pd.DataFrame): 稼働可能時間のDataFrame

    Returns:
        pd.DataFrame: 日付・負荷(分)・稼働可能(分)・超過(分)の列を持つDataFrame
    """
    if load_df.empty:
        total_df = capacity_df.copy()
        total_df["負荷(分)"] = 0.0
    else:
        grouped = load_df.groupby("日付")["負荷(分)"].sum().reset_index()
        total_df = capacity_df.merge(grouped, on="日付", how="left")
        total_df["負荷(分)"] = total_df["負荷(分)"].fillna(0.0)

    total_df["超過(分)"] = (total_df["負荷(分)"] - total_df["稼働可能(分)"]).clip(lower=0.0)
    return total_df


# ------------------------------------------------------------------------------
# 〆切リスクの算出
# ------------------------------------------------------------------------------
def build_risk_df(
    blocks_df: pd.DataFrame,
    capacity_minutes: float,
    today: Optional[date] = None,
    ) -> pd.DataFrame:
    """〆切ブロックごとの必要ペースとリスク区分を算出する

    必要ペース = 補正後残り時間 / 〆切までの残営業日数

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのDataFrame
        capacity_minutes (float): 1営業日あたりの稼働可能時間(分)
        today (Optional[date], optional): 基準日。指定しない場合はESS基準の本日

    Returns:
        pd.DataFrame: 必要ペース・残営業日数・リスク区分を追加したDataFrame
    """
    if today is None:
        today = Task_def.get_ESS_dt().date()

    if blocks_df.empty:
        return pd.DataFrame()

    target_df = blocks_df[blocks_df["〆切"].notna()].copy()
    if target_df.empty:
        return pd.DataFrame()

    business_days_left = []
    required_pace = []
    risk_level = []

    for _, block in target_df.iterrows():
        deadline = block["〆切"]
        corrected_minutes = float(block["補正後残り(分)"])

        if deadline >= today:
            # 〆切日までの残営業日数(本日と〆切日を含む)
            days_left = count_business_days(today, deadline)
            divisor = max(1, days_left)
        else:
            # 〆切超過の場合は超過営業日数を負値で表し、本日中に消化する前提とする
            days_left = -count_business_days(deadline + timedelta(days=1), today)
            divisor = 1

        pace = corrected_minutes / divisor
        business_days_left.append(days_left)
        required_pace.append(pace)

        if deadline < today:
            risk_level.append("〆切超過")
        elif capacity_minutes <= 0:
            risk_level.append("危険")
        elif pace > capacity_minutes:
            risk_level.append("危険")
        elif pace > capacity_minutes * 0.7:
            risk_level.append("注意")
        else:
            risk_level.append("余裕")

    target_df["残営業日数"] = business_days_left
    target_df["必要ペース(分/日)"] = [round(p, 1) for p in required_pace]
    target_df["必要ペース(h/日)"] = [round(p / 60, 2) for p in required_pace]
    target_df["リスク区分"] = risk_level

    return target_df.sort_values(
        ["必要ペース(分/日)"], ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------
# カレンダーイベントの構築
# ------------------------------------------------------------------------------
_WEEKDAY_JA = "月火水木金土日"


def _shift_weekend_to_friday(target_date: date) -> tuple[date, str]:
    """土日を直前の金曜日に寄せ、タイトルに付記する日付ラベルを返す

    Args:
        target_date (date): 元の日付

    Returns:
        tuple[date, str]: 表示日付と、寄せた場合のみ入るラベル(例: "(土 10/24)")
    """
    weekday = target_date.weekday()
    if weekday < 5:
        return target_date, ""
    label = f"({_WEEKDAY_JA[weekday]} {target_date.month}/{target_date.day})"
    return target_date - timedelta(days=weekday - 4), label


def build_calendar_events(
    blocks_df: pd.DataFrame,
    show_deadline: bool = True,
    show_waiting: bool = True,
    today: Optional[date] = None,
    ) -> list[dict]:
    """streamlit-calendar用のイベントリストを作成する

    〆切イベントはサブタスク単位(タスク名+〆切サブ名)、
    待機日イベントはタスク単位(タスク名+未完了かつ最小サブ順序のサブ名)とする。
    〆切・待機日が土日の場合は直前の金曜日に寄せて表示する。

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのDataFrame
        show_deadline (bool, optional): 〆切イベントを表示するか
        show_waiting (bool, optional): 待機日イベントを表示するか
        today (Optional[date], optional): 基準日。指定しない場合はESS基準の本日

    Returns:
        list[dict]: FullCalendar形式のイベント辞書のリスト
    """
    if today is None:
        today = Task_def.get_ESS_dt().date()

    if blocks_df.empty:
        return []

    # オーダ略ごとの配色を作成する (Dashboard3と同一の黄金比配色)
    order_sort_df = Output_G.get_order_sort_df()
    order_labels = order_sort_df["オーダ略称"].tolist()
    color_map = generate_order_colors(order_labels)

    events = []

    # 〆切イベント (サブタスク単位)
    if show_deadline:
        deadline_df = blocks_df[blocks_df["〆切"].notna()]
        for _, block in deadline_df.iterrows():
            deadline = block["〆切"]
            is_overdue = deadline < today
            prefix = "⚠️" if is_overdue else "⏰"
            base_color = color_map.get(block["オーダ略"], "#78909c")

            display_date, date_label = _shift_weekend_to_friday(deadline)

            events.append({
                "title": f"{prefix}{block['タスク名']} / {block['〆切サブ名']}{date_label}",
                "start": display_date.strftime("%Y-%m-%d"),
                "end": display_date.strftime("%Y-%m-%d"),
                "allDay": True,
                "backgroundColor": base_color,
                "borderColor": COLOR_OVERDUE if is_overdue else base_color,
                "textColor": "#ffffff",
                "extendedProps": {
                    "task_id": block["タスクID"],
                    "name": block["タスク名"],
                    "kind": "deadline_date",
                    "subtask_id": block["〆切サブID"],
                    "corrected_minutes": int(block["補正後残り(分)"]),
                },
            })

    # 待機日イベント (タスク単位・タスクごとに1件のみ)
    if show_waiting:
        waiting_df = blocks_df[blocks_df["待機日"].notna()]
        waiting_df = waiting_df.drop_duplicates(subset=["タスクID"], keep="first")
        for _, block in waiting_df.iterrows():
            waiting_date = block["待機日"]
            # 未完了かつ最もサブ順序が小さいサブ名を取得する
            head_subtask_name = _get_head_incomplete_subtask_name(block["タスクID"])
            base_color = color_map.get(block["オーダ略"], "#78909c")

            display_date, date_label = _shift_weekend_to_friday(waiting_date)

            events.append({
                "title": f"⏸️{block['タスク名']} / {head_subtask_name}{date_label}",
                "start": display_date.strftime("%Y-%m-%d"),
                "end": display_date.strftime("%Y-%m-%d"),
                "allDay": True,
                "display": "list-item",
                "backgroundColor": base_color,
                "borderColor": base_color,
                "extendedProps": {
                    "task_id": block["タスクID"],
                    "name": block["タスク名"],
                    "kind": "waiting",
                    "subtask_id": None,
                    "corrected_minutes": 0,
                },
            })

    return events


def _get_head_incomplete_subtask_name(task_id: str) -> str:
    """未完了かつ最もサブタスク順序が小さいサブタスク名を取得する

    待機日イベントはサブタスクと紐付かないため、
    タスクの先頭未完了サブタスク名を表示名に使用する。

    Args:
        task_id (str): タスクID

    Returns:
        str: サブタスク名。取得できない場合は空文字
    """
    # タスクIDの冒頭6文字がすべて数字ならProject/Active、そうでなければDaily/Active
    if len(task_id) >= 6 and task_id[:6].isdigit():
        folder_path = os.path.join("data", "Project", "Active")
    else:
        folder_path = os.path.join("data", "Daily", "Active")

    csv_path = os.path.join(folder_path, f"{task_id}.csv")
    if not os.path.exists(csv_path):
        return ""

    try:
        task = Task_def.read_task_csv(csv_path)
    except Exception:
        return ""

    incomplete_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]
    if incomplete_df.empty:
        return ""

    head_row = incomplete_df.loc[incomplete_df["sort_index"].idxmin()]
    return str(head_row["name"])


if __name__ == "__main__":
    blocks = build_deadline_blocks_df()
    print(blocks)