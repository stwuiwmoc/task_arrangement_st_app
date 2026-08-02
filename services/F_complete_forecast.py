import importlib.util
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def

# data/upload_path/my_upload_folder.py を型安全にインポート
my_upload_folder: Any
try:
    spec = importlib.util.spec_from_file_location(
        "my_upload_folder",
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'upload_path', 'my_upload_folder.py'))
    )
    if spec and spec.loader:
        my_upload_folder = importlib.util.module_from_spec(spec)
        sys.modules["my_upload_folder"] = my_upload_folder
        spec.loader.exec_module(my_upload_folder)
    else:
        raise ImportError("Could not load my_upload_folder module")
except Exception as e:
    raise ImportError(f"my_upload_folderのインポートに失敗しました: {e}")


def output_completed_tasks() -> None:
    """Project/Complete フォルダに存在するタスクcsvを全て結合したcsvを作成する

    Returns:
        None: 返り値なし。出力先フォルダに完了済タスク一覧.csvを作成する
    """

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # completeフォルダに存在するtask csvを全てTaskオブジェクトとして取得
    complete_folder = os.path.join(base_dir, "data", "Project", "Complete")
    tasks = Task_def.read_all_task_csvs(complete_folder)

    # OrderInformationを2インスタンス作成（オーダ管理.csvを優先、見つからない場合のみold参照）
    order_info = Task_def.OrderInformation(os.path.join(base_dir, "data", "オーダ管理.csv"))
    order_info_old = Task_def.OrderInformation(os.path.join(base_dir, "data", "オーダ管理_old.csv"))

    # サブタスク行にタスクID情報を付加する
    all_rows = []
    for task_id, task in tasks.items():
        if task.sub_tasks.empty:
            continue

        order_number = task.order_number or ""

        pj_abbr = order_info.get_project_abbr(order_number)
        if not pj_abbr:
            pj_abbr = order_info_old.get_project_abbr(order_number)

        order_abbr = order_info.get_order_abbr(order_number)
        if not order_abbr:
            order_abbr = order_info_old.get_order_abbr(order_number)

        for _, row in task.sub_tasks.sort_values("sort_index").iterrows():
            # 削除フラグ: 実績時間が0ならTrue、それ以外はFalse
            delete_flag = True if int(row["actual_time"]) == 0 else False

            combined_row = {
                "タスクID+サブID": f"{task_id}{row['subtask_id']}",
                "PJ略": pj_abbr,
                "オーダ番号": order_number,
                "オーダ略称": order_abbr,
                "タスク名": task.name,
                "サブ名": row["name"],
                "見込み": row["estimated_time"],
                "実績": row["actual_time"],
                "当初作業": row["is_initial"],
                "ノミナル": row["is_nominal"],
                "サブ順序": row["sort_index"],
                "削除フラグ": delete_flag,
            }
            all_rows.append(combined_row)

    # タスクID情報を付加したサブタスク全てを一つのDataFrameに結合する
    result_df = pd.DataFrame(all_rows)

    # 結合したDataFrameをcsvとして出力する
    output_path = os.path.join(my_upload_folder.my_upload_folder_path, "完了済タスク一覧.csv")
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return None

if __name__ == "__main__":
    output_completed_tasks()