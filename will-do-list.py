import math
import os
import sys
from datetime import datetime

import pandas as pd
import st_aggrid
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.B_WillDo_create as Output_B
import services.C_WorkLog_record as Output_C
from sidebar import task_view


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
                "values": ["今", "済","着手", "不要", "後回", ""]
            }
        # タスクID列なら太字表示
        if col == "タスクID":
            col_def["cellStyle"] = {"fontWeight": "bold"}
        columnDefs.append(col_def)

    # 行スタイル設定（状態列が「今」の行は背景色変更）
    row_style_jscode = st_aggrid.JsCode("""
        function(params) {
            if (params.data.状態 == "今") {
                return {
                    'color': 'black',
                    'backgroundColor': '#ffff66'
                };
            }
        }
        """)

    gridOptions = {
        "columnDefs": columnDefs,
        "defaultColDef": {
            "resizable": True,
            "sortable": True,
            "filter": use_filter,
            "editable": True
        },
        "getRowStyle": row_style_jscode,
    }

    aggrid_ret = st_aggrid.AgGrid(
        df,
        gridOptions=gridOptions,
        height=400,
        theme="streamlit",
        key="willdo_aggrid",
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        width="stretch",
        editable=True,
    )
    return aggrid_ret


if __name__ == "__main__":
    st.set_page_config(layout="wide")

    task_view.task_sidebar()

    # 表示モード選択
    ESS_dt = Task_def.get_ESS_dt()
    mode = st.radio(
        "表示モード",
        [f"本日分（{ESS_dt.month}/{ESS_dt.day}）表示", "過去分表示"],
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
                value=Output_B.get_without_today_latest_WillDO_date(),
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
        selected_str = ESS_dt.strftime("%y%m%d")

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

            # タイマー処理
            # 状態列が"今"の行数を取得し、行数に応じた処理
            now_count = edited_df[edited_df["状態"] == "今"].shape[0]
            if now_count == 0:
                st.write("「今」が選択されていません")
            elif now_count == 1:
                now_row = edited_df[edited_df["状態"] == "今"].iloc[0]
                st.write(f"**選択中：{now_row['タスクID']} {now_row['サブID']}「{now_row['タスク名']}」の「{now_row['サブ名']}」**")
                radio_minutes = [15, 8, now_row["見込み"], math.ceil(now_row["残時間/日"])]

                col_timer1, col_timer2, col_record = st.columns([9, 3, 5], border=True)

                with col_timer1:
                    # タイマー開始ボタン
                    col_timer1_radio, col_timer1_btn = st.columns([6, 3])
                    with col_timer1_radio:
                        # ラジオボタンで選択肢を作成
                        radio_options = [
                            f"標準{radio_minutes[0]}分",
                            f"標準{radio_minutes[1]}分",
                            f"見込{radio_minutes[2]}分",
                            f"残時間{radio_minutes[3]}分"
                        ]
                        selected_idx = radio_options.index(
                            st.radio(
                                "タイマー選択", radio_options, key="willdo_timer_radio",
                                horizontal=True, label_visibility="collapsed"
                            )
                        )
                    with col_timer1_btn:
                        if st.button(f"{radio_minutes[selected_idx]}分開始", key="willdo_timer1_btn", use_container_width=True):
                            Output_C.start_new_timer_and_record_WorkLog(
                                willdo_date=selected_str,
                                timer_minutes=int(radio_minutes[selected_idx]),
                                task_id=now_row["タスクID"],
                                subtask_id=now_row["サブID"]
                            )
                            st.success("開始しました")

                with col_timer2:
                    # 続けて開始ボタン
                    if st.button(f"続けて開始", key="willdo_timer2_btn", type="tertiary", use_container_width=True):

                        # 続けて開始ボタンを使えるのは、直前サブタスクの終了時刻がまだ来てない場合のみ
                        if datetime.now() < Output_C.check_WorkLog_latest_end_datetime(selected_str):
                            Output_C.continuously_start_and_record_WorkLog(
                                willdo_date=selected_str,
                                task_id=now_row["タスクID"],
                                subtask_id=now_row["サブID"]
                            )
                            st.success("開始しました")
                        else:
                            st.warning("直前のサブタスク終了時刻を過ぎているため、続けて開始できません。新規にタイマーを開始してください。")

                with col_record:
                    # 実績記録ボタン
                    col_record_minute, col_record_btn = st.columns([2, 2])
                    with col_record_minute:
                        custom_minutes = st.number_input(
                            "分数入力", step=1, key="minute_input", placeholder="分", label_visibility="collapsed", value=None
                        )
                        if custom_minutes is None:
                            custom_minutes = 0
                    with col_record_btn:
                        record_button = st.button(
                            f"{custom_minutes}分記録",
                            key="willdo_timer3_btn", use_container_width=True)
                        if record_button:
                            Output_C.record_completed_task_WorkLog(
                                willdo_date=selected_str,
                                achievement_minutes=int(custom_minutes),
                                task_id=now_row["タスクID"],
                                subtask_id=now_row["サブID"]
                            )
                            st.success("記録しました")

            else:
                st.warning("「今」が複数行選択されています")

            # タスクID・サブタスクID指定と会議名・オーダ指定で実績記録操作を2カラムで表示
            col_add1, col_add2 = st.columns([9, 8])

            with col_add1:
                st.markdown("#### Will-doリストにタスク追加", unsafe_allow_html=True)

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
                add_btn = st.button(
                    f"{task_id_input} / {subtask_id_input} を追加",
                    key="willdo_add_btn", use_container_width=True)
                if add_btn:
                    if task_id_input and subtask_id_input:
                        Output_B.add_WillDo_Task_with_ID(task_id_input, subtask_id_input)
                        st.rerun()
                    else:
                        st.warning("タスクIDとサブタスクIDを両方入力してください")

            with col_add2:
                st.markdown("#### 打合せ実績を記録", unsafe_allow_html=True)
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
                col_add2_radio, col_add2_order = st.columns([4, 4])
                with col_add2_radio:
                    meeting_type = st.radio(
                        "打合せ種別",
                        ["突発", "予定"],
                        horizontal=True,
                        key="willdo_meeting_type_radio",
                        label_visibility="collapsed"
                    )
                    if meeting_type == "突発":
                        is_meeting_planned = False
                    else:
                        is_meeting_planned = True
                with col_add2_order:
                    selected_label = st.selectbox(
                        "オーダを選択", order_labels, key="willdo_order_selectbox", label_visibility="collapsed")
                    order_input = order_number_map[selected_label]

                col_add2_minute, col_add2_btn = st.columns([1, 2])
                with col_add2_minute:
                    meeting_minutes = st.number_input(
                        "分数入力", step=1, key="willdo_meeting_minute_input", placeholder="分", label_visibility="collapsed", value=None
                    )
                with col_add2_btn:
                    meeting_record_btn = st.button(
                        f"{meeting_minutes}分記録",
                        key="willdo_add_meeting_minute_btn", use_container_width=True
                    )
                    if meeting_record_btn:
                        if meeting_name_input and (meeting_minutes >= 0):
                            Output_C.record_completed_meeting_WorkLog(
                                willdo_date=selected_str,
                                achievement_minutes=int(meeting_minutes),
                                meeting_name=meeting_name_input,
                                order_number=order_input,
                                is_meeting_planned=is_meeting_planned
                            )
                            st.info("記録しました")
                        else:
                            st.warning("会議名とオーダと分数を全て入力してください")

        else:
            st.info("Will-doリスト未作成です")

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
                    Output_B.create_new_WillDo_with_DailyTasks()
                    st.rerun()
                elif chk_project:
                    Output_B.add_WillDo_all_ProjectTasks()
                    st.rerun()
                else:
                    st.info("何も実行されませんでした。")
