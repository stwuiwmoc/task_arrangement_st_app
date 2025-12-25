import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class SubTask:
    subtask_id: str = field(metadata={"label": "サブID"})  # サブタスクID
    name: str = field(metadata={"label": "サブ名"})  # サブタスク名
    estimated_time: int = field(metadata={"label": "見込み"})  # 見込み時間
    actual_time: int = field(metadata={"label": "実績"})  # 実績時間
    is_initial: bool = field(metadata={"label": "当初作業"}) # 当初作業フラグ
    is_nominal: bool = field(metadata={"label": "ノミナル"})  # ノミナルフラグ
    sort_index: int = field(metadata={"label": "サブ順序"}) # サブタスク順序
    is_incomplete: bool = field(metadata={"label": "未完了"})  # 未完了フラグ
    deadline_date: Optional[str] = field(default=None, metadata={"label": "〆切"})  # 〆切日
    deadline_reason: Optional[str] = field(default=None, metadata={"label": "理由"})  # 〆切理由

    @classmethod
    def attr_map(cls, attr: str) -> str:
        """SubTaskクラスの属性名を日本語ラベルに変換"""
        if attr in cls.__dataclass_fields__ and "label" in cls.__dataclass_fields__[attr].metadata:
            return cls.__dataclass_fields__[attr].metadata["label"]
        return attr

@dataclass
class Task:
    task_id: str = field(metadata={"label": "タスクID"})
    name: str = field(metadata={"label": "タスク名"})
    order_number: str = field(metadata={"label": "オーダ番号"})
    sub_tasks: Dict[str, SubTask] = field(default_factory=dict, metadata={"label": "サブタスク辞書"})
    waiting_date: Optional[str] = field(default=None, metadata={"label": "待機日"})

    def add_subtask(self, subtask: SubTask):
        """
        サブタスクを追加する。

        Args:
            subtask (SubTask): 追加するサブタスクオブジェクト
        """
        self.sub_tasks[subtask.subtask_id] = subtask

    def save_to_csv(self) -> None:
        """
        現在のTaskオブジェクトの情報をタスクcsvファイルに上書き保存する。
        保存先フォルダはタスクIDの冒頭6文字が数字ならProject/Active、そうでなければDaily/Active。
        ヘッダは9行固定、10行目からサブタスク行。
        """
        if len(self.task_id) >= 6 and self.task_id[:6].isdigit():
            folder_path = os.path.join("data", "Project", "Active")
        else:
            folder_path = os.path.join("data", "Daily", "Active")

        file_path = os.path.join(folder_path, f"{self.task_id}.csv")

        # ヘッダー9行固定
        header_lines = [
            f"{self.name}\n",
            f"{self.waiting_date if self.waiting_date else ''}\n",
            f"{self.order_number if self.order_number else ''}\n"
        ]
        header_lines += ["\n"] * (9 - len(header_lines))
        # サブタスク部分
        subtask_lines = []
        for subtask in self.sub_tasks.values():
            row = [
                subtask.subtask_id,
                subtask.name,
                str(subtask.estimated_time),
                str(subtask.actual_time),
                subtask.deadline_date if subtask.deadline_date else "",
                subtask.deadline_reason if subtask.deadline_reason else "",
                str(subtask.is_initial),
                str(subtask.is_nominal),
                str(subtask.sort_index),
                str(subtask.is_incomplete)
            ]
            subtask_lines.append(",".join(row) + "\n")
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(header_lines + subtask_lines)

# --- タスクcsvファイルを読み込む関数 ---
def read_task_csv(file_path: str) -> Task:
    """1つのタスクCSVファイルからTaskオブジェクトを生成する。

    Args:
        file_path (str): タスクCSVファイルのパス

    Returns:
        Task: 読み込んだTaskオブジェクト
    """
    # ヘッダー9行固定
    with open(file_path, 'r', encoding='utf-8') as f:
        header_lines = []
        for _ in range(9):
            line = f.readline()
            header_lines.append(line.strip().strip(','))

    task_name = header_lines[0] if len(header_lines) > 0 else ""
    waiting_date = header_lines[1] if len(header_lines) > 1 and header_lines[1] else None
    order_number = header_lines[2] if len(header_lines) > 2 and header_lines[2] else None

    # 10行目からサブタスク
    skiprows = 9

    sub_tasks = {}
    try:
        subtasks_df = pd.read_csv(file_path, skiprows=skiprows, header=None)
        for _, row in subtasks_df.iterrows():
            subtask = SubTask(
                subtask_id=row[0],
                name=row[1],
                estimated_time=int(row[2]),
                actual_time=int(row[3]),
                deadline_date=row[4] if pd.notna(row[4]) and row[4] != '' else None,
                deadline_reason=row[5] if pd.notna(row[5]) and row[5] != '' else None,
                is_initial=bool(row[6]),
                is_nominal=bool(row[7]),
                sort_index=float(row[8]),
                is_incomplete=bool(row[9])
            )
            sub_tasks[subtask.subtask_id] = subtask
    except pd.errors.EmptyDataError:
        pass

    task_id = os.path.splitext(os.path.basename(file_path))[0]
    return Task(
        task_id=task_id,
        name=task_name,
        order_number=order_number,
        waiting_date=waiting_date,
        sub_tasks=sub_tasks
    )

def read_all_task_csvs(folder_path: str) -> Dict[str, Task]:
    """指定フォルダ内のCSVファイルからタスク情報を全件読み込む。

    Args:
        folder_path (str): タスクCSVファイルが格納されているディレクトリのパス。

    Returns:
        Dict[str, Task]: タスクIDをキー、Taskオブジェクトを値とする辞書。
    """
    tasks = {}
    for filename in os.listdir(folder_path):
        if filename.endswith('.csv'):
            file_path = os.path.join(folder_path, filename)
            task = read_task_csv(file_path)
            tasks[task.task_id] = task
    return tasks


@dataclass
class WillDoEntry:
    status: Optional[str] = field(metadata={"label": "状態"})  # 状態
    project_abbr: str = field(metadata={"label": "PJ略"})  # プロジェクト略称
    order_abbr: str = field(metadata={"label": "オーダ略"})  # オーダ略称

    task_id: str = field(metadata={"label": "タスクID"})  # タスクID
    subtask_id: str = field(metadata={"label": "サブID"})  # サブタスクID
    task_name: str = field(metadata={"label": "タスク名"})  # タスク名
    subtask_name: str = field(metadata={"label": "サブ名"})  # サブタスク名
    estimated_time: int = field(metadata={"label": "見込み"})  # 見込み時間

    daily_work_time: Optional[int] = field(default=None, metadata={"label": "残時間/日"})  # 1日あたり作業時間
    deadline_date_nearest: Optional[str] = field(default=None, metadata={"label": "直近〆切"})  # 〆切日

    @classmethod
    def attr_map(cls, attr: str) -> str:
        """WillDoEntryクラスの属性名を日本語ラベルに変換"""
        if attr in cls.__dataclass_fields__ and "label" in cls.__dataclass_fields__[attr].metadata:
            return cls.__dataclass_fields__[attr].metadata["label"]
        return attr

class OrderInformation:
    """
    オーダ管理CSVを読み込み、オーダ番号から各種情報を取得するクラス。
    """

    def __init__(self, csv_path: str = os.path.join("data", "オーダ管理.csv")):
        """
        Args:
            csv_path (str): オーダ管理CSVファイルのパス
        """
        self.df = pd.read_csv(
            csv_path, dtype=str, header=None,
            names=["order_number", "project_abbr", "order_abbr", "order_fullname"])

    def get_project_abbr(self, order_number: str) -> str:
        """
        オーダ番号からプロジェクト略称を取得する。

        Args:
            order_number (str): オーダ番号

        Returns:
            str: プロジェクト略称（見つからない場合は空文字）
        """
        row = self.df[self.df["order_number"] == order_number]
        if not row.empty:
            return row.iloc[0]["project_abbr"]
        return ""

    def get_order_abbr(self, order_number: str) -> str:
        """
        オーダ番号からオーダ略称を取得する。

        Args:
            order_number (str): オーダ番号

        Returns:
            str: オーダ略称（見つからない場合は空文字）
        """
        row = self.df[self.df["order_number"] == order_number]
        if not row.empty:
            return row.iloc[0]["order_abbr"]
        return ""

    def get_order_fullname(self, order_number: str) -> str:
        """
        オーダ番号からオーダ正式名称を取得する。

        Args:
            order_number (str): オーダ番号

        Returns:
            str: オーダ正式名称（見つからない場合は空文字）
        """
        row = self.df[self.df["order_number"] == order_number]
        if not row.empty:
            return row.iloc[0]["order_fullname"]
        return ""
