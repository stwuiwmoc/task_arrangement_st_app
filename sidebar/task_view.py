import os
import sys

import pandas as pd
import st_aggrid
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def


def task_sidebar():
    # タスクIDとタスク名一覧取得
    with st.sidebar:
        folder_option = st.radio(
            "タスクフォルダ選択",
            ["進行中タスクを表示", "完了済タスクを表示"],
            index=0,
            label_visibility="collapsed",
            horizontal=True
        )
        if folder_option == "進行中タスクを表示":
            task_choices, task_id_to_csv = get_task_choices(
                choice_from_active=True,
                include_task_name=True
            )
        else:
            task_choices, task_id_to_csv = get_task_choices(
                choice_from_active=False,
                include_task_name=True
            )


    selected_label = st.sidebar.selectbox("タスクIDを選択", sorted(task_choices), label_visibility="collapsed") if task_choices else None

    task = None
    if selected_label:
        csv_path = task_id_to_csv[selected_label]
        task = Task_def.read_task_csv(csv_path)
        order_info = Task_def.OrderInformation()
        pj_abbr = order_info.get_project_abbr(task.order_number)
        order_abbr = order_info.get_order_abbr(task.order_number)

        # オーダ情報表示
        col11, col12, col13 = st.sidebar.columns([2, 1, 1])
        col11.write(f"{task.order_number}")
        col12.write(f"{pj_abbr}")
        col13.write(f"{order_abbr}")

        # 待機日表示
        st.sidebar.write(f"待機日: {task.waiting_date if task.waiting_date else 'None'}")

        # サブタスク一覧表示
        subtask_dicts = []
        for sub in task.sub_tasks.values():
            subtask_dicts.append({
                "ID": sub.subtask_id,
                "サブ名": sub.name,
                "見込": sub.estimated_time,
                "実績": sub.actual_time,
                "〆切": sub.deadline_date,
                "理由": sub.deadline_reason,
                "当初": sub.is_initial,
                "ノミナル": sub.is_nominal,
                "順序": sub.sort_index,
                "未完": sub.is_incomplete
            })
        df = pd.DataFrame(subtask_dicts)

        # 列順を指定: 順序→残り
        desired_order = ["順序"]
        rest_cols = [c for c in df.columns if c not in desired_order]
        df = df[desired_order + rest_cols]

        # DataFrameの"未完"列をbool型に変換
        if "未完" in df.columns:
            df["未完"] = df["未完"].astype(bool)

        # 順序列で昇順ソート
        if "順序" in df.columns:
            df = df.sort_values("順序").reset_index(drop=True)

        # サブID最大値とサブタスク順序最大値をcolsで表示＋ラジオボタンを右側に配置
        with st.sidebar:
            filter_option = st.radio(
                "サブタスク表示フィルター",
                ["未完了サブタスクのみ", "全サブタスク表示"],
                index=0,
                label_visibility="collapsed",
                horizontal=True
            )
            if filter_option == "未完了サブタスクのみ":
                filtered_df = df[df["未完"] == True].reset_index(drop=True)
            else:
                filtered_df = df.reset_index(drop=True)

            # AGGrid表示用のカラム定義を作成
            columnDefs = []
            for col in filtered_df.columns:
                width = int(calc_col_width(filtered_df[col]))
                if col == "未完":
                    columnDefs.append({
                        "headerName": col,
                        "field": col,
                        "width": width,
                        "filter": "agSetColumnFilter",
                        "cellRenderer": "agCheckboxCellRenderer"
                    })
                elif col == "サブ順序":
                    columnDefs.append({
                        "headerName": col,
                        "field": col,
                        "width": width,
                        "filter": "agNumberColumnFilter"
                    })
                else:
                    columnDefs.append({
                        "headerName": col,
                        "field": col,
                        "width": width,
                        "filter": "agTextColumnFilter"
                    })

            gridOptions = {
                "columnDefs": columnDefs,
                "defaultColDef": {
                    "resizable": True,
                    "sortable": True,
                    "filter": True
                }
            }

            st.markdown(
                """
                <style>
                .ag-theme-streamlit {
                    overflow-x: auto !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st_aggrid.AgGrid(
                filtered_df,
                gridOptions=gridOptions,
                height=300,
                theme="streamlit",
                key="subtasks_aggrid",
                fit_columns_on_grid_load=False,
                enable_enterprise_modules=True,
                allow_unsafe_jscode=True,
                width="content"
            )

        # --- サブタスク追加機能 ---

        # 最大サブID+1を自動設定
        if task.sub_tasks:
            max_subtask_id = max(int(sub.subtask_id[1:]) for sub in task.sub_tasks.values())
        else:
            max_subtask_id = 0
        new_subtask_id = f"#{max_subtask_id+1:03d}"
        st.sidebar.markdown(f"#### サブタスク追加（追加されるサブID：{new_subtask_id}）")

        add_col1, add_col2, add_col3 = st.sidebar.columns([3, 1, 1])
        with add_col1:
            new_name = st.text_input(
                label="サブタスク名",
                key="new_subtask_name",
                label_visibility="collapsed",
                placeholder="サブタスク名"
            )
        with add_col2:
            new_sort_index = st.text_input(
                label="サブ順序",
                key="new_subtask_sort_index",
                label_visibility="collapsed",
                placeholder="サブ順序"
            )
        with add_col3:
            if st.button("追加", key="add_subtask_btn"):
                if not new_name or not new_sort_index:
                    st.warning("サブタスク名とサブ順序は必須です。")
                else:
                    try:
                        sort_index_val = int(new_sort_index)
                    except ValueError:
                        st.warning("サブ順序は数値で入力してください。")
                    else:
                        # SubTaskの自動設定
                        new_subtask = Task_def.SubTask(
                            subtask_id=new_subtask_id,
                            name=new_name,
                            estimated_time=15,
                            actual_time=0,
                            deadline_date=None,
                            deadline_reason=None,
                            is_initial=False,
                            is_nominal=True,
                            sort_index=sort_index_val,
                            is_incomplete=True
                        )
                        task.add_subtask(new_subtask)
                        task.save_to_csv()
                        st.success(f"サブタスク {new_subtask_id} を追加しました。")
                        st.rerun()
    return task


# 列幅自動調整
def calc_col_width(
        series, min_width=80, max_width=400, padding=3, use_padding=True
        ) -> int:
    """
    列の最大文字数からAGGrid用のカラム幅(px)を計算する。

    Args:
        series (pd.Series): 列データ
        min_width (int): 最小幅(px)
        max_width (int): 最大幅(px)
        padding (int): 追加する文字数分のパディング
        use_padding (bool): パディングを使う場合True

    Returns:
        int: 計算されたカラム幅(px)
    """
    maxlen = series.astype(str).map(len).max() if not series.empty else 0
    pad = padding if use_padding else 0
    return min(max(min_width, (maxlen + pad) * 12), max_width)


def get_task_choices(
        choice_from_active: bool,
        include_task_name: bool) -> tuple[list[str], dict[str, str]]:
    """
    Project/Active配下のタスクID一覧を取得し、リストで返す。

    Args:
        choice_from_active (bool): Trueの場合はActiveフォルダ、Falseの場合はCompleteフォルダから取得
        include_task_name (bool): Trueの場合は「タスクID：タスク名」、Falseの場合は「タスクID」のみでリスト化

    Returns:
        tuple[list[str], dict[str, str]]:
            - タスク選択肢リスト
            - 選択肢ラベル→csvパスの辞書
    """
    folder_type = "Active" if choice_from_active else "Complete"
    project_dir = os.path.join("data", "Project", folder_type)
    task_choices = []
    task_id_to_csv = {}
    if os.path.exists(project_dir):
        for fname in os.listdir(project_dir):
            if fname.endswith(".csv"):
                task_id = os.path.splitext(fname)[0]
                csv_path = os.path.join(project_dir, fname)
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        task_name = f.readline().strip()
                    if include_task_name:
                        label = f"{task_id}：{task_name}"
                    else:
                        label = task_id
                except Exception:
                    label = f"{task_id}：(読み込み失敗)" if include_task_name else task_id
                task_choices.append(label)
                task_id_to_csv[label] = csv_path
    return task_choices, task_id_to_csv


def get_subtask_choices(task_id: str, include_subtask_name: bool) -> list[str]:
    """
    指定タスクIDのサブタスクID一覧を取得し、リストで返す。

    Args:
        task_id (str): 対象タスクID
        include_subtask_name (bool): Trueの場合は「サブID：サブ名」、Falseの場合は「サブID」のみでリスト化

    Returns:
        list[str]: サブタスク選択肢リスト
    """
    project_dir = os.path.join("data", "Project", "Active")
    csv_path = os.path.join(project_dir, f"{task_id}.csv")
    choices = []
    if os.path.exists(csv_path):
        task = Task_def.read_task_csv(csv_path)
        for sub in task.sub_tasks.values():
            if include_subtask_name:
                label = f"{sub.subtask_id}：{sub.name}"
            else:
                label = sub.subtask_id
            choices.append(label)
    return choices


if __name__ == "__main__":
    # st.title("タスクビューア表示テスト用ページ")
    task_sidebar()
    pass  # タブで直接表示しない
