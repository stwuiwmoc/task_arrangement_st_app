import os
import sys
from datetime import datetime

import pandas as pd
import st_aggrid
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.B_WillDo_create as WillDo_create
from sidebar import task_view


def get_latest_WillDO_date() -> datetime.date:
    """Will-doリストの本日を除く最新日付を取得する。

    Returns:
        datetime.date: 本日を除く最新日付。存在しない場合はNone。
    """
    willdo_dir = os.path.join("data", "WillDo")
    if not os.path.exists(willdo_dir):
        return ""

    willdo_files = [
        f for f in os.listdir(willdo_dir)
        if f.startswith("WillDo") and f.endswith(".csv")
    ]
    dates = []
    for filename in willdo_files:
        date_str = filename[len("WillDo"):len("WillDo") + 6]
        try:
            date_obj = datetime.strptime(date_str, "%y%m%d").date()
            if date_obj < datetime.now().date():
                dates.append(date_obj)
        except ValueError:
            continue

    if not dates:
        return ""

    latest_date = max(dates)
    return latest_date


def WillDo_display_settings(
        df: pd.DataFrame, use_filter: bool) -> st_aggrid.AgGrid:
    """Willdoリスト表示の共通設定

    Args:
        df (pd.DataFrame): 表示するデータフレーム
        use_filter (bool): フィルタ機能を有効にするかどうか

    Returns:
        st_aggrid.AgGrid: AgGridコンポーネント
    """
    # 列幅自動調整
    columnDefs = []
    for col in df.columns:
        width = int(
            task_view.calc_col_width(df[col], use_padding=False))
        col_def = {
            "headerName": col,
            "field": col,
            "width": width,
            "filter": use_filter,
            "editable": True
        }
        # 状態列ならプルダウン指定（cellEditor="agSelectCellEditor"を明示し、editableもTrueにする）
        if col == "状態":
            col_def["cellEditor"] = "agSelectCellEditor"
            col_def["cellEditorParams"] = {
                "values": ["済", "不要", "後回", "", "1着", "済2", "2着", "済3"]
            }
        columnDefs.append(col_def)

    gridOptions = {
        "columnDefs": columnDefs,
        "defaultColDef": {
            "resizable": True,
            "sortable": True,
            "filter": use_filter,
            "editable": True
        }
    }

    aggrid_ret = st_aggrid.AgGrid(
        df,
        gridOptions=gridOptions,
        height=400,
        theme="streamlit",
        key="willdo_aggrid",
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
        allow_unsafe_jscode=False,
        width="stretch",
        editable=True,
    )
    return aggrid_ret


if __name__ == "__main__":
    st.set_page_config(layout="wide")

    task_view.task_sidebar()

    # 表示モード選択
    mode = st.radio(
        "表示モード",
        [f"本日分（{datetime.now().month}/{datetime.now().day}）表示", "過去分表示"],
        horizontal=True, label_visibility="collapsed")

    if mode == "過去分表示":
        # 選択日付のWill-doリストcsv表示

        # 日付選択（2カラム構成：左に説明、右に日付選択）
        col_left, col_right = st.columns([2, 3])
        with col_left:
            st.markdown("#### Will-doリスト日付選択")
        with col_right:
            selected_date = st.date_input(
                "日付を選択してください",
                value=get_latest_WillDO_date(),
                key="willdo_date_input",
                label_visibility="collapsed"
            )
        selected_str = selected_date.strftime("%y%m%d")

        willdo_dir = os.path.join("data", "WillDo")
        willdo_file = os.path.join(willdo_dir, f"WillDo{selected_str}.csv")

        if os.path.exists(willdo_file):
            df_past = pd.read_csv(willdo_file, encoding="utf-8-sig")
            # 過去分の場合は表示のみ
            WillDo_display_settings(df_past, use_filter=True)
        else:
            st.info("Will-doリスト未作成です")

    else:
        # 本日分のWill-doリストcsv表示
        selected_str = datetime.now().date().strftime("%y%m%d")

        willdo_dir = os.path.join("data", "WillDo")
        willdo_file = os.path.join(willdo_dir, f"WillDo{selected_str}.csv")
        if os.path.exists(willdo_file):
            df_today = pd.read_csv(willdo_file, encoding="utf-8-sig")

            # テーブル表示の詳細設定
            aggrid_ret = WillDo_display_settings(df_today, use_filter=False)

            # 差分があれば自動保存
            edited_df = aggrid_ret["data"] if "data" in aggrid_ret else df_today
            if not edited_df.equals(df_today):
                edited_df.to_csv(willdo_file, index=False, encoding="utf-8-sig")

        else:
            st.info("Will-doリスト未作成です")

        # タイマー処理関連
        st.markdown("#### タイマー処理関連", unsafe_allow_html=True)
        st.write("Step2でここに実装予定")

        # タスクID・サブタスクID指定と会議名・オーダ指定でWillDo追加を横並びで表示
        st.markdown("#### Will-doリストにタスクを追加", unsafe_allow_html=True)
        col_add1, col_blank, col_add2 = st.columns([2, 1, 2])

        with col_add1:
            st.markdown("タスクID・サブタスクIDを指定", unsafe_allow_html=True)

            # タスクID一覧を取得しセレクトボックスで選択
            task_choices, task_id_to_csv = task_view.get_task_choices(
                choice_from_active=True,
                include_task_name=True)
            task_id_label = st.selectbox(
                "タスクIDを選択", sorted(task_choices), key="willdo_taskid_selectbox", label_visibility="collapsed"
            )
            # ラベルからタスクIDのみ抽出
            if task_choices:
                task_id_input = task_id_label.split("：")[0]
            else:
                task_id_input = task_id_label

            # サブタスクID一覧を取得しセレクトボックスで選択
            subtask_choices = task_view.get_subtask_choices(task_id_input, include_subtask_name=True)
            subtask_id_label = st.selectbox(
                "サブタスクIDを選択", subtask_choices, key="willdo_subtaskid_selectbox", label_visibility="collapsed"
            )
            # ラベルからサブタスクIDのみ抽出
            if subtask_choices:
                subtask_id_input = subtask_id_label.split("：")[0]
            else:
                subtask_id_input = subtask_id_label

            # 追加ボタン押下でWillDoにタスク追加
            add_btn = st.button("追加", key="willdo_add_btn")
            if add_btn:
                if task_id_input and subtask_id_input:
                    WillDo_create.add_WillDo_Task_with_ID(task_id_input, subtask_id_input)
                    st.rerun()
                else:
                    st.warning("タスクIDとサブタスクIDを両方入力してください")

        # col_blankは何も表示しない（空白用）

        with col_add2:
            st.markdown("会議名・オーダを指定", unsafe_allow_html=True)
            # OrderInformationクラスからオーダ番号一覧と略称取得
            order_info = Task_def.OrderInformation()
            order_numbers = order_info.df["order_number"].dropna().unique().tolist()
            order_labels = []
            order_number_map = {}
            for order_number in order_numbers:
                pj_abbr = order_info.get_project_abbr(order_number)
                order_abbr = order_info.get_order_abbr(order_number)
                label = f"{pj_abbr} / {order_abbr}"
                order_labels.append(label)
                order_number_map[label] = order_number

            meeting_name_input = st.text_input(
                "会議名", key="willdo_meetingname", placeholder="会議名", label_visibility="collapsed")
            selected_label = st.selectbox(
                "オーダを選択", order_labels, key="willdo_order_selectbox", label_visibility="collapsed")
            order_input = order_number_map[selected_label]
            add_meeting_btn = st.button("追加", key="willdo_add_meeting_btn")
            if add_meeting_btn:
                if meeting_name_input and order_input:
                    WillDo_create.add_WillDo_meeting(meeting_name_input, order_input)
                    st.rerun()
                else:
                    st.warning("会議名とオーダを両方入力してください")

        # Will-doリスト初期化操作を2カラムで表示（チェックボックス方式）
        st.markdown("#### Will-doリスト初期化", unsafe_allow_html=True)
        col_chk, col_exec = st.columns([2, 1])

        # チェックボックスの値リセットは、rerun後に初期値を渡すことで対応
        # Streamlitの仕様上、セッションステートで直接値を変更できないため、keyを変更して強制リセット
        if "willdo_chk_reset_id" not in st.session_state:
            st.session_state["willdo_chk_reset_id"] = 0

        chk_daily = chk_project = False
        with col_chk:
            chk_daily = st.checkbox(
                "デイリータスクのみの新規Will-doリストを作成",
                key=f"willdo_chk_daily_{st.session_state['willdo_chk_reset_id']}"
            )
            chk_project = st.checkbox(
                "プロジェクトタスクをWill-doリストに追加",
                key=f"willdo_chk_project_{st.session_state['willdo_chk_reset_id']}"
            )
        with col_exec:
            if st.button("初期化実行", key="willdo_init_exec"):
                # 実行後にkeyを変更してチェックボックスをリセット
                st.session_state["willdo_chk_reset_id"] += 1
                if chk_daily:
                    WillDo_create.create_new_WillDo_with_DailyTasks()
                    st.rerun()
                elif chk_project:
                    WillDo_create.add_WillDo_all_ProjectTasks()
                    st.rerun()
                else:
                    st.info("何も実行されませんでした。")
