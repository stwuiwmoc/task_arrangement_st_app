import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import pandera.pandas as pa
from pandera.typing import DataFrame, Series


# --- PanderaでサブタスクDataFrameのスキーマを定義 ---
class SubTaskSchema(pa.DataFrameModel):
    """サブタスクDataFrameのPanderaスキーマ定義"""
    subtask_id: Series[str] = pa.Field(nullable=False, description="サブタスクID")
    name: Series[str] = pa.Field(nullable=False, description="サブタスク名")
    estimated_time: Series[int] = pa.Field(nullable=False, ge=0, description="見込み時間")
    actual_time: Series[int] = pa.Field(nullable=False, ge=0, description="実績時間")
    deadline_date: Series[str] = pa.Field(nullable=True, description="〆切日")
    deadline_reason: Series[str] = pa.Field(nullable=True, description="〆切理由")
    is_initial: Series[bool] = pa.Field(nullable=False, description="当初作業フラグ")
    is_nominal: Series[bool] = pa.Field(nullable=False, description="ノミナルフラグ")
    sort_index: Series[float] = pa.Field(nullable=False, description="サブタスク順序")
    is_incomplete: Series[bool] = pa.Field(nullable=False, description="未完了フラグ")

    class Config:
        coerce = True  # 型変換を許可

    @staticmethod
    def attr_map(attr: str) -> str:
        """属性名を日本語短縮ラベルに変換"""
        label_map = {
            "subtask_id": "サブID",
            "name": "サブ名",
            "estimated_time": "見込み",
            "actual_time": "実績",
            "deadline_date": "〆切",
            "deadline_reason": "理由",
            "is_initial": "当初作業",
            "is_nominal": "ノミナル",
            "sort_index": "サブ順序",
            "is_incomplete": "未完了",
        }
        return label_map.get(attr, attr)


def get_subtask_schema_columns() -> list[str]:
    """SubTaskSchemaのカラム名リストを取得する。

    Returns:
        list[str]: カラム名のリスト
    """
    return list(SubTaskSchema.to_schema().columns.keys())


def create_empty_subtask_df() -> pd.DataFrame:
    """空のサブタスクDataFrameを作成"""
    return pd.DataFrame(columns=get_subtask_schema_columns())


@dataclass
class Task:
    task_id: str = field(metadata={"label": "タスクID"})
    name: str = field(metadata={"label": "タスク名"})
    order_number: str = field(metadata={"label": "オーダ番号"})
    sub_tasks: pd.DataFrame = field(default_factory=create_empty_subtask_df, metadata={"label": "サブタスクDF"})
    waiting_date: Optional[str] = field(default=None, metadata={"label": "待機日"})

    def add_subtask(self, subtask_row: dict):
        """
        サブタスクを1行dictで追加する。

        Args:
            subtask_row (dict): サブタスク情報の辞書
                例: {"subtask_id": "#001", "name": "作業名", ...}
        """
        # SubTaskSchemaのカラム名と一致するか検証
        schema_columns = set(SubTaskSchema.to_schema().columns)
        row_keys = set(subtask_row.keys())
        if not row_keys.issubset(schema_columns):
            invalid_keys = row_keys - schema_columns
            raise ValueError(f"Invalid keys in subtask_row: {invalid_keys}. Expected keys: {schema_columns}")

        # deadline_date, deadline_reasonの空値をNoneに正規化
        for key in ("deadline_date", "deadline_reason"):
            if key in subtask_row and (subtask_row[key] == "" or pd.isna(subtask_row[key])):
                subtask_row[key] = None

        # サブタスクを追加
        new_row = pd.DataFrame([subtask_row])
        if self.sub_tasks.empty:
            self.sub_tasks = new_row
        else:
            self.sub_tasks = pd.concat([self.sub_tasks, new_row], ignore_index=True)

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
        if not self.sub_tasks.empty:
            for _, row in self.sub_tasks.iterrows():
                row_data = [
                    str(row["subtask_id"]),
                    str(row["name"]),
                    str(int(row["estimated_time"])),
                    str(int(row["actual_time"])),
                    str(row["deadline_date"]) if pd.notna(row["deadline_date"]) and row["deadline_date"] else "",
                    str(row["deadline_reason"]) if pd.notna(row["deadline_reason"]) and row["deadline_reason"] else "",
                    str(row["is_initial"]),
                    str(row["is_nominal"]),
                    str(row["sort_index"]),
                    str(row["is_incomplete"])
                ]
                subtask_lines.append(",".join(row_data) + "\n")
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

    try:
        subtasks_df = pd.read_csv(
            file_path, skiprows=skiprows, header=None,
            names=["subtask_id", "name", "estimated_time", "actual_time",
                   "deadline_date", "deadline_reason", "is_initial", "is_nominal",
                   "sort_index", "is_incomplete"]
        )
        # 型変換
        subtasks_df["estimated_time"] = subtasks_df["estimated_time"].astype(int)
        subtasks_df["actual_time"] = subtasks_df["actual_time"].astype(int)
        subtasks_df["is_initial"] = subtasks_df["is_initial"].astype(bool)
        subtasks_df["is_nominal"] = subtasks_df["is_nominal"].astype(bool)
        subtasks_df["sort_index"] = subtasks_df["sort_index"].astype(float)
        subtasks_df["is_incomplete"] = subtasks_df["is_incomplete"].astype(bool)
        # 空文字をNoneに変換
        subtasks_df["deadline_date"] = subtasks_df["deadline_date"].replace("", None)
        subtasks_df["deadline_reason"] = subtasks_df["deadline_reason"].replace("", None)
        # Panderaでバリデーション
        subtasks_df = SubTaskSchema.validate(subtasks_df)
    except pd.errors.EmptyDataError:
        subtasks_df = create_empty_subtask_df()

    task_id = os.path.splitext(os.path.basename(file_path))[0]
    return Task(
        task_id=task_id,
        name=task_name,
        order_number=order_number,
        waiting_date=waiting_date,
        sub_tasks=subtasks_df
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

def get_ESS_dt() -> datetime:
    """ESS（勤務管理システム）と同じルールで現在日時を取得する。
    具体的には、ESSの勤務日付は午前5時に切り替わるため、現在時刻から5時間引いた日時を返す。

    Returns:
        datetime: ESS基準の現在日時
    """
    return datetime.now() - timedelta(hours=5)
