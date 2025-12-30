import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List

import jpholiday
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models.Task_definition as Task_def

# -------------------------------------------------------------
# wordの各項と対応する関数
# -------------------------------------------------------------

def create_new_WillDo_with_DailyTasks():
    """2.2.1項
    デイリータスクを元に新しいWill-doリストを作成し保存する。

    Returns:
        None
    """
    # 全デイリータスクで既存の全サブタスクを完了状態にして保存
    complete_all_SubTasks_in_DailyTasks()

    # Will-doリストDataFrameを初期化
    WillDo_df = pd.DataFrame(
        columns=[col.metadata["label"] for col in Task_def.WillDoEntry.__dataclass_fields__.values()])

    # 最新のWillDoファイルを特定
    target_date = get_latest_WillDo_date()

    # マッチするデイリータスクCSVを読み込み
    dates_since_target = get_dates_since_date(target_date)
    Daily_tasks_dict = get_matched_DailyTasks(dates_since_target)

    # デイリータスクの初期化処理
    Daily_tasks_dict = add_DailyTasks_today_SubTask(Daily_tasks_dict)

    # Will-doエントリをDataFrameに追加
    WillDo_df = add_WillDo_Tasks(WillDo_df, Daily_tasks_dict)

    # Will-doリストDataFrameを保存 ファイル名: data/WillDo/WillDoyymmdd.csv
    ESS_dt_str = Task_def.get_ESS_dt().strftime('%y%m%d')
    willdo_file_path = os.path.join(
        "data", "WillDo", f"WillDo{ESS_dt_str}.csv")
    WillDo_df.to_csv(willdo_file_path, index=False, encoding="utf-8-sig")
    return


def add_WillDo_all_ProjectTasks() -> None:
    """2.2.2項
    既存のWill-doリストを読み込んでActiveかつ待機中ではないProjectタスク全てを追加する。

    Returns:
        None
    """
    ESS_dt_str = Task_def.get_ESS_dt().strftime('%y%m%d')
    WillDo_df = pd.read_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        encoding="utf-8-sig")

    project_active_dir = os.path.join("data", "Project", "Active")
    Project_tasks_dict = Task_def.read_all_task_csvs(project_active_dir)
    WillDo_df = add_WillDo_Tasks(WillDo_df, Project_tasks_dict)

    WillDo_df.to_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        index=False, encoding="utf-8-sig")

    return WillDo_df


# 2.2.3項はstreamlit上の機能で足りるため省略


def add_WillDo_Task_with_ID(
        task_id: str,
        subtask_id: str,
        ) -> None:
    """2.2.4項
    指定したタスクIDとサブタスクIDに基づいてWill-doリストに既存のサブタスクを追加する。

    Args:
        task_id (str): タスクID
        subtask_id (str): サブタスクID
    """

    # Will-doリストcsvを読み込み
    ESS_dt_str = Task_def.get_ESS_dt().strftime('%y%m%d')
    WillDo_df = pd.read_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        encoding="utf-8-sig")

    # タスクIDとサブタスクIDからWillDoEntryを生成
    WillDo_entry = ID_to_WillDoEntry(task_id, subtask_id)

    # Will-doリストDataFrameに追加
    entry_dict = {
        Task_def.WillDoEntry.attr_map(k): v
        for k, v in asdict(WillDo_entry).items()}
    try:
        new_entry_df = pd.DataFrame([entry_dict])

        # 空または全てNAの列を除外して結合
        new_entry_df = new_entry_df.dropna(how='all', axis=1)
        WillDo_df = pd.concat([WillDo_df, new_entry_df], ignore_index=True)

    except Exception as e:
        raise ValueError(f"Error while processing DataFrame: {e}")

    # Will-doリストDataFrameを保存
    WillDo_df.to_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        index=False, encoding="utf-8-sig")
    return


def add_WillDo_meeting(
        meeting_name: str,
        order_number: str
        ) -> None:
    """2.2.5項
    既存のWill-doリストを読み込み、当日の会議予定を追加する。

    Args:
        meeting_name (str): 会議名
        order_number (str): オーダ番号

    Returns:
        None
    """
    # Will-doリストcsvを読み込み
    ESS_dt_str = Task_def.get_ESS_dt().strftime('%y%m%d')
    WillDo_df = pd.read_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        encoding="utf-8-sig")

    # オーダ情報取得
    Order_info = Task_def.OrderInformation()

    # 会議予定の取得とWillDoEntryへの変換
    meeting_entry = Task_def.WillDoEntry(
        status=None,
        project_abbr=Order_info.get_project_abbr(order_number),
        order_abbr=Order_info.get_order_abbr(order_number),
        task_id="打合せ",
        subtask_id="",
        task_name=meeting_name,
        subtask_name="",
        estimated_time=0,
        daily_work_time=None,
        deadline_date_nearest=Task_def.get_ESS_dt().strftime('%Y-%m-%d')
    )

    # Will-doリストDataFrameに追加
    entry_dict = {
        Task_def.WillDoEntry.attr_map(k): v
        for k, v in asdict(meeting_entry).items()}

    try:
        new_entry_df = pd.DataFrame([entry_dict])

        # 空または全てNAの列を除外して結合
        new_entry_df = new_entry_df.dropna(how='all', axis=1)
        WillDo_df = pd.concat(
            [WillDo_df, new_entry_df],
            ignore_index=True)
    except Exception as e:
        raise ValueError(f"Error while adding entry to WillDo_df: {e}")

    # Will-doリストDataFrameを保存
    WillDo_df.to_csv(
        os.path.join("data", "WillDo", f"WillDo{ESS_dt_str}.csv"),
        index=False, encoding="utf-8-sig")
    return

# -------------------------------------------------------------
# 上記の関数で使用する補助関数群
# ------------------------------------------------------------
def get_latest_WillDo_date() -> datetime:
    """
    最新のWillDoリストの日付を取得する。

    Returns:
        datetime: 最新WillDoリストの日付（datetime型）

    Raises:
        FileNotFoundError: WillDoリストファイルが見つからない場合。
        ValueError: ファイル名が期待する形式でない場合。
    """
    def _extract_date_from_filename(filename: str) -> datetime:
        """
        ファイル名から日付情報を抽出してdatetime型で返す。

        Args:
            filename (str): ファイル名（例: "工数実績251017.csv"）

        Returns:
            datetime: ファイル名から抽出した日付（datetime型）

        Raises:
            ValueError: ファイル名が期待する形式でない場合。
        """
        match = re.match(r"WillDo(\d{6})\.csv", filename)
        if match:
            return datetime.strptime(match.group(1), "%y%m%d")
        else:
            raise ValueError(f"Filename {filename} does not match expected pattern.")

    worklog_dir = os.path.join("data", "WillDo")
    files = [f for f in os.listdir(worklog_dir) if re.match(r"WillDo\d{6}\.csv", f)]
    if not files:
        raise FileNotFoundError("WillDoリストファイルが見つかりません。")

    latest_file = max(files, key=_extract_date_from_filename)
    latest_date = _extract_date_from_filename(latest_file)
    return latest_date

def get_dates_since_date(date: datetime) -> list[datetime]:
    """
    指定日翌日から今日までの日付リストを返す。

    Args:
        date (datetime): 基準日（この翌日から今日までをリスト化）

    Returns:
        list[datetime]: 指定日翌日から今日までの各日付（datetime.date型）のリスト。
    """
    today = Task_def.get_ESS_dt().date()
    date_list = []
    d = date.date() + timedelta(days=1)
    while d <= today:
        date_list.append(d)
        d += timedelta(days=1)
    return date_list


def get_matched_DailyTasks(date_list: list[datetime]) -> Dict[str, Task_def.Task]:
    """
    日付リストからデイリータスクcsv名の3,4,5文字目となる識別子リストを作成し、
    マッチするデイリータスクのCSVを読み込み、
    Taskオブジェクトの辞書を返す。

    Args:
        date_list (list[datetime]): 日付リスト

    Returns:
        Dict[str, Task_def.Task]: タスクIDをキー、Taskオブジェクトを値とする辞書
    """

    filenames = []

    # 日次タスクの追加
    filenames.append("Day")

    # 週次タスクの追加
    for date in date_list:
        # 日付リストから曜日の英単語の先頭3文字を取得（例: Mon, Tue, Wed ...）
        day_of_week = date.strftime("%a").capitalize()
        filenames.append(day_of_week)

    # 月次タスクの追加
    for date in date_list:
        # 日付リストから「月の何日目か」を取得
        day_of_month = date.day
        filenames.append(f"M{day_of_month:02d}")

    daily_active_dir = os.path.join("data", "Daily", "Active")
    matching_tasks = {}
    for filename in filenames:
        # yyXXXnnn.csv のXXXがfilenameと一致するファイル名をリストアップ
        matched_files = [
            f for f in os.listdir(daily_active_dir)
            if len(f) >= 9 and f.endswith(".csv") and f[2:5] == filename
        ]
        for csvfile in matched_files:
            csv_path = os.path.join(daily_active_dir, csvfile)
            task_obj = Task_def.read_task_csv(csv_path)

            # Taskオブジェクトを辞書に追加
            matching_tasks[task_obj.task_id] = task_obj
    return matching_tasks

def complete_all_SubTasks_in_DailyTasks() -> None:
    """デイリータスクの全サブタスクを完了状態にして保存

    Returns:
        None
    """
    daily_active_dir = os.path.join("data", "Daily", "Active")
    for fname in os.listdir(daily_active_dir):
        if fname.endswith(".csv"):
            csv_path = os.path.join(daily_active_dir, fname)
            task = Task_def.read_task_csv(csv_path)
            task.sub_tasks["is_incomplete"] = False
            task.save_to_csv()
    return


def add_DailyTasks_today_SubTask(
        Daily_tasks_dict: Dict[str, Task_def.Task]
        ) -> Dict[str, Task_def.Task]:
    """デイリータスクにその日分のサブタスクを追加して保存

    Args:
        Daily_tasks_dict (Dict[str, Task_def.Task]): デイリータスクの辞書

    Returns:
        Dict[str, Task_def.Task]: 更新されたデイリータスクの辞書
    """
    for task in Daily_tasks_dict.values():
        # サブタスクID #000をコピーしたサブタスクを追加するための準備
        base_row = task.sub_tasks[task.sub_tasks["subtask_id"] == "#000"]
        if base_row.empty:
            continue
        base_subtask = base_row.iloc[0]

        # サブタスクIDとサブタスク順序は、既存すべてのサブタスクの最大値+1とする
        existing_subtask_ids = [int(sid[1:]) for sid in task.sub_tasks["subtask_id"].tolist()]
        existing_subtask_sort_indexes = task.sub_tasks["sort_index"].tolist()
        new_subtask_id = f"#{max(existing_subtask_ids) + 1:03d}"
        new_sort_index = max(existing_subtask_sort_indexes) + 1
        # サブタスク名は、"コピー元サブタスク名yymmdd"とする
        new_subtask_name = f"{base_subtask['name']}{datetime.now().strftime('%y%m%d')}"

        # スキーマベースで辞書生成
        cols = Task_def.get_subtask_schema_columns()
        copied_subtask = {col: None for col in cols}
        copied_subtask.update({
            "subtask_id": new_subtask_id,
            "name": new_subtask_name,
            "estimated_time": base_subtask["estimated_time"],
            "actual_time": base_subtask["actual_time"],
            "deadline_date": datetime.now().strftime('%Y-%m-%d'),
            "deadline_reason": base_subtask["deadline_reason"],
            "is_initial": base_subtask["is_initial"],
            "is_nominal": base_subtask["is_nominal"],
            "sort_index": new_sort_index,
            "is_incomplete": True
        })
        task.add_subtask(copied_subtask)

        # 更新したTaskオブジェクトをタスクCSVに保存
        task.save_to_csv()

        # Taskオブジェクトを辞書に追加
        Daily_tasks_dict[task.task_id] = task

    return Daily_tasks_dict

def ID_to_WillDoEntry(task_id: str, subtask_id: str) -> Task_def.WillDoEntry:
    """タスクIDとサブタスクIDからWillDoEntryオブジェクトを生成する。

    Args:
        task_id (str): タスクID
        subtask_id (str): サブタスクID

    Returns:
        WillDoEntry: 生成されたWillDoEntryオブジェクト
    """
    # タスクIDの冒頭6文字がすべて数字ならProject/Active、そうでなければDaily/Active
    if len(task_id) >= 6 and task_id[:6].isdigit():
        folder_path = os.path.join("data", "Project", "Active")
    else:
        folder_path = os.path.join("data", "Daily", "Active")

    # タスクとサブタスクを取得
    task = Task_def.read_task_csv(os.path.join(folder_path, f"{task_id}.csv"))
    subtask_row = task.sub_tasks[task.sub_tasks["subtask_id"] == subtask_id]
    if subtask_row.empty:
        raise ValueError(f"サブタスク {subtask_id} が見つかりません")
    subtask = subtask_row.iloc[0]

    # オーダ情報を取得
    Order_info = Task_def.OrderInformation()

    # 1. 未完了サブタスクをsort_index順に並べる
    incomplete_subtasks_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True].sort_values("sort_index")
    incomplete_subtask_ids = incomplete_subtasks_df["subtask_id"].tolist()

    # 2. subtask_idより順番が小さい未完了サブタスクを除外
    try:
        base_idx = incomplete_subtask_ids.index(subtask_id)
    except ValueError:
        base_idx = 0  # subtask_idが見つからない場合は先頭から

    filtered_subtasks_df = incomplete_subtasks_df.iloc[base_idx:]

    # 3. 残った未完了サブタスクの中で最も古い〆切日を持つサブタスクを特定
    subtasks_with_deadline_df = filtered_subtasks_df[filtered_subtasks_df["deadline_date"].notna()]
    if not subtasks_with_deadline_df.empty:
        nearest_row = subtasks_with_deadline_df.loc[subtasks_with_deadline_df["deadline_date"].idxmin()]
        nearest_deadline = datetime.strptime(nearest_row["deadline_date"], "%Y-%m-%d").date()
        nearest_subtask_id = nearest_row["subtask_id"]

        # 4. 3で取得したサブタスクより順番が大きい未完了サブタスクを除外
        filtered_ids = filtered_subtasks_df["subtask_id"].tolist()
        try:
            end_idx = filtered_ids.index(nearest_subtask_id)
        except ValueError:
            end_idx = len(filtered_ids) - 1
        target_subtasks_df = filtered_subtasks_df.iloc[:end_idx+1]

        # 5. 4で取得したサブタスク全ての（見込み時間 - 実績時間）を合算
        estimated_time_sum = (
            target_subtasks_df["estimated_time"] - target_subtasks_df["actual_time"]
        ).sum() if not target_subtasks_df.empty else 0

        # 今日から〆切日までの日本の祝日を除いた平日日数を取得
        today = datetime.now().date()
        end_date = nearest_deadline
        days_left = 0
        d = today
        while d <= end_date:
            if d.weekday() < 5 and not jpholiday.is_holiday(d):
                days_left += 1
            d += timedelta(days=1)

        if days_left is not None and days_left <= 1:
            # 〆切日までの日数が1以下の場合は、合算時間をそのまま一日当たり作業時間目安とする
            estimated_time_per_day = estimated_time_sum
        else:
            # そうでない場合は、合算時間を〆切日までの日数で割った値を一日当たり作業時間目安とする
            estimated_time_per_day = round(estimated_time_sum / (days_left - 0.5), 0)

    else:
        # 〆切日を持つサブタスクが存在しない場合
        nearest_deadline = None
        nearest_subtask_id = None

        # 残りのサブタスク全ての（見込み時間 - 実績時間）を合算
        estimated_time_per_day = (
            filtered_subtasks_df["estimated_time"] - filtered_subtasks_df["actual_time"]
        ).sum() if not filtered_subtasks_df.empty else 0

    # WillDoEntryオブジェクトを生成して返す
    return Task_def.WillDoEntry(
        status=None,
        project_abbr=Order_info.get_project_abbr(task.order_number),
        order_abbr=Order_info.get_order_abbr(task.order_number),
        task_id=task.task_id,
        subtask_id=subtask["subtask_id"],
        task_name=task.name,
        subtask_name=subtask["name"],
        estimated_time=subtask["estimated_time"],
        daily_work_time=estimated_time_per_day,
        deadline_date_nearest=nearest_deadline
    )


def add_WillDo_Tasks(WillDo_df: pd.DataFrame, Tasks_dict: Dict[str, Task_def.Task]) -> pd.DataFrame:
    """
    Taskオブジェクトの辞書からWill-doエントリをDataFrameに追加する。

    Args:
        Tasks_dict (Dict[str, Task_def.Task]): タスクIDをキー、Taskオブジェクトを値とする辞書

    Returns:
        pd.DataFrame: Will-doエントリを含むDataFrame
    """

    for task in Tasks_dict.values():
        # 待機日が設定されている場合はスキップ
        if task.waiting_date is not None:
            continue
        # 未完了かつ最もsort_indexが小さいサブタスクを抽出
        incomplete_subtasks_df = task.sub_tasks[task.sub_tasks["is_incomplete"] == True]
        if not incomplete_subtasks_df.empty:
            subtask_row = incomplete_subtasks_df.loc[incomplete_subtasks_df["sort_index"].idxmin()]
            will_do_entry = ID_to_WillDoEntry(task.task_id, subtask_row["subtask_id"])
            # WillDoEntryをDataFrameに変換して追加
            entry_dict = {
                Task_def.WillDoEntry.attr_map(k): v
                for k, v in asdict(will_do_entry).items()}
            try:
                new_entry_df = pd.DataFrame([entry_dict])

                # 空または全てNAの列を除外して結合
                new_entry_df = new_entry_df.dropna(how='all', axis=1)
                WillDo_df = pd.concat(
                    [WillDo_df, new_entry_df],
                    ignore_index=True)
            except Exception as e:
                raise ValueError(f"Error while adding entry to WillDo_df: {e}")

    return WillDo_df


if __name__ == "__main__":
    create_new_WillDo_with_DailyTasks()
    # add_WillDo_all_ProjectTasks()
