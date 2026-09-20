import math
import os
import sys
from datetime import datetime, timedelta

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
                "values": ["今", "済", "着手", "不要", "後回", ""]
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
        update_on=["cellValueChanged"],  # セル編集時にデータを返す
    )
    return aggrid_ret

# 入力値が半角数字以外ならNoneにする関数
def sanitize_halfwidth_digit(val: str) -> str | None:
    """
    入力値が半角数字（0-9）のみで構成されていればそのまま返し、
    それ以外（全角数字や記号、空文字、Noneなど）はNoneを返す。

    Args:
        val (str): 入力値（文字列またはNone）

    Returns:
        str | None: 半角数字のみならその値、そうでなければNone
    """
    if val is not None and (val.isdigit() and all('0' <= c <= '9' for c in val)):
        return val
    return None


def get_edited_dataframe(aggrid_ret, df_original: pd.DataFrame) -> pd.DataFrame:
    """AgGridの返却値から編集後のDataFrameを取得する（streamlit-aggrid v1.x対応）

    Args:
        aggrid_ret: AgGridの返却値
        df_original: 元のDataFrame

    Returns:
        pd.DataFrame: 編集後のDataFrame（元のDataFrameと同じ列のみ）
    """
    # 内部列を除いた元の列リスト
    original_cols = [c for c in df_original.columns if not c.startswith("::")]

    # v1.x系: 属性として .data でアクセス
    if hasattr(aggrid_ret, 'data') and aggrid_ret.data is not None:
        edited_df = aggrid_ret.data.copy()
        # 内部列を除去
        cols_to_keep = [c for c in edited_df.columns if not c.startswith("::")]
        edited_df = edited_df[cols_to_keep]
        # 列順を元のDataFrameに合わせる（共通の列のみ）
        common_cols = [c for c in original_cols if c in edited_df.columns]
        edited_df = edited_df[common_cols]
        return edited_df
    # 旧バージョン互換: 辞書形式でアクセス
    if isinstance(aggrid_ret, dict) and "data" in aggrid_ret:
        return aggrid_ret["data"]
    return df_original


def load_willdo_csv(filepath: str) -> pd.DataFrame:
    """WillDoリストのCSVを読み込み、内部列を除去して返す

    Args:
        filepath: CSVファイルのパス

    Returns:
        pd.DataFrame: 内部列を除去したDataFrame
    """
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    # 内部列（::auto_unique_id::など）を除去
    internal_cols = [c for c in df.columns if c.startswith("::")]
    if internal_cols:
        df = df.drop(columns=internal_cols)
        # CSVファイルから内部列を除去した状態で上書き保存
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return df


def sort_willdo_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """WillDoリストを表示用に並べ替える。
    「残時間/日」降順でソートし、直近〆切が存在しない行を先頭に移動し、最後に状態が済・不要・後回の行を末尾に移動する。

    Args:
        df (pd.DataFrame): WillDoリストのDataFrame

    Returns:
        pd.DataFrame: 並べ替え後のDataFrame
    """
    done_statuses = ["済", "不要", "後回"]

    def _sort(group_df: pd.DataFrame) -> pd.DataFrame:
        if "直近〆切" in group_df.columns:
            has_dl = group_df["直近〆切"].notna() & (group_df["直近〆切"].astype(str).str.strip() != "")
            return (group_df.assign(_has_deadline=has_dl)
                    .sort_values(["_has_deadline", "残時間/日", "タスクID"], ascending=[True, False, True])
                    .drop(columns=["_has_deadline"]))
        return group_df.sort_values(["残時間/日", "タスクID"], ascending=[False, True])

    df_active = _sort(df[~df["状態"].isin(done_statuses)])
    df_done = _sort(df[df["状態"].isin(done_statuses)])
    return pd.concat([df_active, df_done], ignore_index=True)


def has_dataframe_changed(edited_df: pd.DataFrame, original_df: pd.DataFrame) -> bool:
    """2つのDataFrameに差分があるか判定（型の違いを吸収）

    Args:
        edited_df: 編集後のDataFrame
        original_df: 元のDataFrame

    Returns:
        bool: 差分がある場合True
    """
    if edited_df.shape != original_df.shape:
        return True
    if list(edited_df.columns) != list(original_df.columns):
        return True
    # 値を文字列化して比較（型の違いを吸収）
    for col in edited_df.columns:
        if not edited_df[col].astype(str).equals(original_df[col].astype(str)):
            return True
    return False


def find_task_csv_path(task_id: str) -> str | None:
    """タスクIDに対応するCSVファイルのパスをDaily/Active・Project/Activeから検索して返す。

    Args:
        task_id (str): 検索するタスクID

    Returns:
        str | None: 見つかったCSVファイルのパス。見つからない場合はNone。
    """
    search_dirs = [
        os.path.join("data", "Daily", "Active"),
        os.path.join("data", "Project", "Active"),
    ]
    for d in search_dirs:
        candidate = os.path.join(d, f"{task_id}.csv")
        if os.path.exists(candidate):
            return candidate
    return None


def get_incomplete_subtasks_df(task_id: str) -> pd.DataFrame | None:
    """タスクIDに属する未完了サブタスクをsort_index昇順で取得して返す。

    Args:
        task_id (str): 対象のタスクID

    Returns:
        pd.DataFrame | None: 未完了サブタスクのDataFrame（順序・サブID・サブタスク名・見込(分)列）。
                             CSVが見つからない場合はNone。
    """
    task_csv_path = find_task_csv_path(task_id)
    if task_csv_path is None:
        return None
    task_now = Task_def.read_task_csv(task_csv_path)
    incomplete_df = (
        task_now.sub_tasks[task_now.sub_tasks["is_incomplete"] == True]
        .sort_values("sort_index")
        .reset_index(drop=True)
    )
    return incomplete_df[["subtask_id", "estimated_time", "actual_time", "name"]].rename(columns={
        "subtask_id": "サブID",
        "estimated_time": "見込",
        "actual_time": "実績",
        "name": "サブタスク名",
    })


def resolve_willdo_file(selected_str: str) -> str:
    willdo_main = os.path.join("data", "WillDo", f"WillDo{selected_str}.csv")
    willdo_old = os.path.join("data", "WillDo", "old", f"WillDo{selected_str}.csv")
    return willdo_main if os.path.exists(willdo_main) else willdo_old


def _render_now_task_subtasks(now_count: int, edited_df: pd.DataFrame) -> None:
    if now_count == 0:
        st.write("「今」が選択されていません")
        return

    if now_count == 1:
        now_row = edited_df[edited_df["状態"] == "今"].iloc[0]
        incomplete_subtasks_df = get_incomplete_subtasks_df(now_row["タスクID"])
        if incomplete_subtasks_df is not None:
            st.dataframe(incomplete_subtasks_df, hide_index=True, width='stretch')
        else:
            st.write("タスクCSVが見つかりません")


def _render_timer_start_controls(now_row: pd.Series, selected_str: str) -> None:
    radio_minutes = [15, 8, now_row["見込み"], math.ceil(now_row["残時間/日"])]
    col_timer1_radio, col_timer1_btn = st.columns([6, 2])
    with col_timer1_radio:
        radio_options = [
            f"標準{radio_minutes[0]}分",
            f"標準{radio_minutes[1]}分",
            f"見込{radio_minutes[2]}分",
            f"残/日{radio_minutes[3]}分"
        ]
        selected_idx = radio_options.index(
            st.radio(
                "タイマー選択", radio_options, key="willdo_timer_radio",
                horizontal=True, label_visibility="collapsed"
            )
        )
    with col_timer1_btn:
        if st.button(f"{radio_minutes[selected_idx]}分  \n開始", key="willdo_timer1_btn", width='stretch'):
            Output_C.start_new_timer_and_record_WorkLog(
                willdo_date=selected_str,
                timer_minutes=int(radio_minutes[selected_idx]),
                task_id=now_row["タスクID"],
                subtask_id=now_row["サブID"]
            )
            st.success("開始")


def _render_timer_continue_button(now_row: pd.Series, selected_str: str) -> None:
    if st.button(f"続けて  \n開始", key="willdo_timer2_btn", type="tertiary", width='stretch'):
        if datetime.now() < Output_C.check_WorkLog_latest_end_datetime(selected_str):
            Output_C.continuously_start_and_record_WorkLog(
                willdo_date=selected_str,
                task_id=now_row["タスクID"],
                subtask_id=now_row["サブID"]
            )
            st.success("開始")
        else:
            st.warning("直前のサブタスク終了時刻を過ぎているため、続けて開始できません。新規にタイマーを開始してください。")


def _validate_worklog_chronology(
    selected_str: str,
    achievement_minutes: str,
    wraptime_minutes: str,
    ) -> bool:
    new_end = datetime.now() - timedelta(minutes=int(wraptime_minutes))
    new_start = new_end - timedelta(minutes=int(achievement_minutes))
    conflict_start = Output_C.get_WorkLog_conflict_last_start_time(selected_str, new_start)
    if conflict_start is not None:
        st.warning(f"工数実績csv既存行の開始時刻は {conflict_start.strftime('%H:%M')} のため、入力値では時系列が矛盾します")
        return False
    return True


def _render_task_record_controls(now_row: pd.Series, selected_str: str) -> None:
    col_record_task_minute, col_record_task_wraptime, col_record_task_btn = st.columns([2.5, 2.5, 2])
    with col_record_task_minute:
        task_achievement_minutes = st.text_input(
            "分数入力", key="minute_input", placeholder="実績", label_visibility="collapsed", value=None
        )
        task_achievement_minutes = sanitize_halfwidth_digit(task_achievement_minutes)
    with col_record_task_wraptime:
        task_wraptime_minutes = st.text_input(
            "経過時間", key="wraptime_input", placeholder="終了後経過", label_visibility="collapsed", value=None
        )
        task_wraptime_minutes = sanitize_halfwidth_digit(task_wraptime_minutes)
    with col_record_task_btn:
        record_button = st.button(
            f"{task_achievement_minutes}分  \n記録",
            key="willdo_timer3_btn", width='stretch')
        if record_button:
            if (task_achievement_minutes is not None) and (task_wraptime_minutes is not None):
                if _validate_worklog_chronology(selected_str, task_achievement_minutes, task_wraptime_minutes):
                    Output_C.record_completed_task_WorkLog(
                        willdo_date=selected_str,
                        achievement_minutes=int(task_achievement_minutes),
                        wraptime_minutes=int(task_wraptime_minutes),
                        task_id=now_row["タスクID"],
                        subtask_id=now_row["サブID"]
                    )
                    st.success("記録")
            else:
                st.warning("分数を両方入力してください")


def _build_order_options() -> tuple[list[str], dict[str, str]]:
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
    return order_labels, order_number_map


def _render_meeting_record_controls(selected_str: str) -> None:
    st.markdown("#### 打合せ実績を記録", unsafe_allow_html=True)
    order_labels, order_number_map = _build_order_options()

    meeting_name_input = st.text_input(
        "会議名", key="willdo_meetingname", placeholder="会議名", label_visibility="collapsed")
    col_record_meeting_order, col_record_meeting_radio = st.columns([6, 4])
    with col_record_meeting_radio:
        meeting_type = st.radio(
            "打合せ種別",
            ["突発", "予定"],
            horizontal=True,
            key="willdo_meeting_type_radio",
            label_visibility="collapsed"
        )
        is_meeting_planned = meeting_type != "突発"
    with col_record_meeting_order:
        selected_label = st.selectbox(
            "オーダを選択", order_labels, key="willdo_order_selectbox", label_visibility="collapsed")
        order_input = order_number_map[selected_label]

    col_record_achievement_minute, col_record_wraptime_minute, col_record_meeting_btn = st.columns([3, 3, 4])
    with col_record_achievement_minute:
        meeting_minutes = st.text_input(
            "分数入力", key="willdo_meeting_minute_input", placeholder="実績", label_visibility="collapsed", value=None
        )
        meeting_minutes = sanitize_halfwidth_digit(meeting_minutes)
    with col_record_wraptime_minute:
        wraptime_minutes = st.text_input(
            "経過時間", key="willdo_meeting_wraptime_input", placeholder="終了後経過", label_visibility="collapsed", value=None
        )
        wraptime_minutes = sanitize_halfwidth_digit(wraptime_minutes)
    with col_record_meeting_btn:
        meeting_record_btn = st.button(
            f"{meeting_minutes}分記録",
            key="willdo_add_meeting_minute_btn", width='stretch'
        )
        if meeting_record_btn:
            if meeting_name_input and (meeting_minutes is not None) and (wraptime_minutes is not None):
                if _validate_worklog_chronology(selected_str, meeting_minutes, wraptime_minutes):
                    Output_C.record_completed_meeting_WorkLog(
                        willdo_date=selected_str,
                        achievement_minutes=int(meeting_minutes),
                        wraptime_minutes=int(wraptime_minutes),
                        meeting_name=meeting_name_input,
                        order_number=order_input,
                        is_meeting_planned=is_meeting_planned
                    )
                    st.info("記録")
            else:
                st.warning("会議名とオーダと分数を全て入力してください")


def _get_default_task_choice_index(task_choices: list[str], edited_df: pd.DataFrame) -> int:
    now_task_default_index = 0
    if task_choices:
        now_rows = edited_df[edited_df["状態"] == "今"]
        if not now_rows.empty:
            now_task_id = now_rows.iloc[0]["タスクID"]
            for index, label in enumerate(task_choices):
                if label.split("：")[0] == now_task_id:
                    now_task_default_index = index
                    break
    return now_task_default_index


def _render_add_task_controls(edited_df: pd.DataFrame) -> None:
    st.markdown("#### Will-doにタスク追加", unsafe_allow_html=True)

    task_choices, _task_id_to_csv = task_view.get_task_choices(
        choice_from_active=True,
        include_task_name=True)
    sorted_task_choices = sorted(task_choices)
    now_task_default_index = _get_default_task_choice_index(sorted_task_choices, edited_df)
    task_id_label = st.selectbox(
        "タスクIDを選択", sorted_task_choices, index=now_task_default_index,
        key="willdo_taskid_selectbox", label_visibility="collapsed"
    )
    task_id_input = task_id_label.split("：")[0] if task_choices else task_id_label

    subtask_choices = task_view.get_subtask_choices(task_id_input, include_subtask_name=True)
    subtask_id_label = st.selectbox(
        "サブタスクIDを選択", subtask_choices, key="willdo_subtaskid_selectbox", label_visibility="collapsed"
    )
    subtask_id_input = subtask_id_label.split("：")[0] if subtask_choices else subtask_id_label

    add_btn = st.button(
        f"{task_id_input} / {subtask_id_input} を追加",
        key="willdo_add_btn", width='stretch')
    if add_btn:
        if task_id_input and subtask_id_input:
            Output_B.add_WillDo_Task_with_ID(task_id_input, subtask_id_input)
            st.rerun()
        else:
            st.warning("タスクIDとサブタスクIDを両方入力してください")


def _render_now_task_actions(now_count: int, edited_df: pd.DataFrame, selected_str: str) -> None:
    # タイマー処理と実績記録処理とタスク追加処理を表示
    if now_count == 0:
        st.write("「今」が選択されていません")
    elif now_count == 1:
        now_row = edited_df[edited_df["状態"] == "今"].iloc[0]

        col_timer1, col_timer2, col_record_task = st.columns([8, 2, 8], border=True)

        with col_timer1:
            _render_timer_start_controls(now_row, selected_str)

        with col_timer2:
            _render_timer_continue_button(now_row, selected_str)

        with col_record_task:
            _render_task_record_controls(now_row, selected_str)

    else:
        st.warning("「今」が複数行選択されています")

    col_add_task, col_record_meeting = st.columns([8, 10])

    with col_record_meeting:
        _render_meeting_record_controls(selected_str)

    with col_add_task:
        _render_add_task_controls(edited_df)


def _render_willdo_section(selected_str: str) -> None:
    willdo_file = resolve_willdo_file(selected_str)
    if os.path.exists(willdo_file):
        df_today = load_willdo_csv(willdo_file)
        # 表示用に並べ替え: 残時間/日降順・完了系を末尾へ
        df_today = sort_willdo_for_display(df_today)

        # 比較用に元のDataFrameをコピー（AgGridが元のdfを変更するため）
        df_original = df_today.copy()

        # テーブル表示の詳細設定
        aggrid_ret = WillDo_display_settings(df_today, use_filter=False)

        # 差分があれば自動保存（streamlit-aggrid v1.x対応）
        edited_df = get_edited_dataframe(aggrid_ret, df_original)
        if has_dataframe_changed(edited_df, df_original):
            edited_df.to_csv(willdo_file, index=False, encoding="utf-8-sig")

        # 状態列が"今"の行数を取得し、行数に応じた処理をするための準備
        now_count = edited_df[edited_df["状態"] == "今"].shape[0]

        col_following_subtasks, col_functions = st.columns([2, 5])
        with col_following_subtasks:
            _render_now_task_subtasks(now_count, edited_df)
        with col_functions:
            _render_now_task_actions(now_count, edited_df, selected_str)
    else:
        st.info("Will-doリスト未作成です")


def _render_willdo_init_section() -> None:
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


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    # 本日分のWill-doリストcsv表示
    ess_dt = Task_def.get_ESS_dt()
    selected_str = ess_dt.strftime("%y%m%d")

    _render_willdo_section(selected_str)
    _render_willdo_init_section()
