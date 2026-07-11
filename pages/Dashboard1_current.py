import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import st_aggrid
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.G_dashboard_aggregation as Output_G
from sidebar import task_view


def render_kpi_cards(df: pd.DataFrame):
    """KPIカードを表示する

    Args:
        df (pd.DataFrame): KPIデータを含むDataFrame
    """
    today = Task_def.get_ESS_dt().date()
    one_week = today + timedelta(days=7)

    week_deadline = sum(
        1 for d in df["直近〆切"]
        if d and Output_G._parse_date_str(d) <= one_week
    )

    waiting_tasks = sum(
        1 for w in df["待機日"] if w is not None
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Activeプロジェクトタスク数", f"{len(df)} 件")
    c2.metric("残見込み総計", f"{df['残見込み(分)'].sum()/60:.1f} h")
    c3.metric("直近1週間〆切タスク数", f"{week_deadline} 件")
    c4.metric("待機中タスク数", f"{waiting_tasks} 件")
    return


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """表示するdfへのフィルタ用セレクトボックス表示・フィルタ適用関数

    Args:
        df (pd.DataFrame): フィルタ対象のDataFrame

    Returns:
        pd.DataFrame: フィルタ後のDataFrame
    """
    f1, f2, f3 = st.columns(3)
    with f1:
        opts = ["すべて"] + sorted(df["PJ略"].dropna().unique().tolist())
        pj = st.selectbox("PJ略", opts, key="filter_pj")

    with f2:
        opts = ["すべて"] + sorted(df["オーダ略"].dropna().unique().tolist())
        order = st.selectbox("オーダ略", opts, key="filter_order")

    with f3:
        opts = ["すべて", "〆切未定", "〆切超過", "完了間近", "〆切迫る", "未着手", "着手済"]
        status = st.selectbox("状態", opts, key="filter_status")

    filtered_df = df.copy()
    if pj != "すべて":
        filtered_df = filtered_df[filtered_df["PJ略"] == pj]
    if order != "すべて":
        filtered_df = filtered_df[filtered_df["オーダ略"] == order]
    if status != "すべて":
        filtered_df = filtered_df[filtered_df["状態"] == status]

    return filtered_df


def render_progress_table(df: pd.DataFrame):
    if df.empty:
        st.warning("表示するタスクがありません。")
        return

    # 進捗率バー
    progress_renderer = st_aggrid.JsCode("""
    class ProgressBarRenderer {
        init(params) {
            const val = params.value || 0;
            let color = '#4caf50';
            if (val < 30) color = '#f44336';
            else if (val < 70) color = '#ff9800';
            this.eGui = document.createElement('div');
            this.eGui.style.cssText = 'background:#eee;width:100%;height:20px;position:relative;border-radius:3px;';
            this.eGui.innerHTML = '<div style="background:' + color + ';width:' + val + '%;height:100%;border-radius:3px;"></div>'
                + '<div style="position:absolute;top:0;left:0;width:100%;text-align:center;line-height:20px;font-size:12px;font-weight:bold;color:#333;">' + val + '%</div>';
        }
        getGui() { return this.eGui; }
    }
    """)

    # 状態バッジ
    status_renderer = st_aggrid.JsCode("""
    class StatusBadgeRenderer {
        init(params) {
            const val = params.value || '';
            const colorMap = {
                "〆切未定": "#000000", // Black
                "〆切超過": "#f44336", // Red
                "完了間近": "#0000ff", // Blue
                "〆切迫る": "#ff9800", // Orange
                "未着手": "#9e9e9e", // Gray
                "着手済": "#4caf50", // Green
            };
            const c = colorMap[val] || "#9e9e9e";
            this.eGui = document.createElement('span');
            this.eGui.style.cssText = 'background:' + c + ';color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;';
            this.eGui.innerText = val;
        }
        getGui() { return this.eGui; }
    }
    """)

    gb = st_aggrid.GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    gb.configure_column("タスクID", width=200, pinned="left")
    gb.configure_column("タスク名", width=500, pinned="left")
    gb.configure_column("状態", cellRenderer=status_renderer, width=200, pinned="left")
    gb.configure_column("進捗率(%)", cellRenderer=progress_renderer, width=200, pinned="left")
    gb.configure_selection(selection_mode="single", use_checkbox=False)

    ret = st_aggrid.AgGrid(
        df,
        gridOptions=gb.build(),
        height=None, # auto height
        theme="streamlit",
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        update_mode=st_aggrid.GridUpdateMode.SELECTION_CHANGED,
        key="progress_table_aggrid",
    )

    # 行選択→サイドバー反映
    selected = ret.get("selected_rows")
    if selected is not None:
        if isinstance(selected, pd.DataFrame) and not selected.empty:
            sel_row = selected.iloc[0]
        elif isinstance(selected, list) and len(selected) > 0:
            sel_row = selected[0]
        else:
            return

        label = f"{sel_row['タスクID']}：{sel_row['タスク名']}"
        if st.session_state.get("selected_task_label") != label:
            st.session_state["selected_task_label"] = label
            st.rerun()  # サイドバーのselectboxを更新するためにページをリロード

    return

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()
    st.markdown("#### 現状ダッシュボード")

    # Activeタスクの横断集計を取得
    df_active = Output_G.build_active_task_summary_df()

    if df_active.empty:
        st.warning("Activeタスクが存在しません。")
        st.stop()

    # KPIカードを表示
    render_kpi_cards(df_active)

    # フィルタを表示
    df_filtered = render_filters(df_active)

    # タブ表示
    tab_a, tab_b, tab_c = st.tabs([
        "進捗テーブル",
        "カンバンボード（未実装）",
        "残見込みTreemap（未実装）"
    ])

    with tab_a:
        st.caption(f"表示中：{len(df_filtered)} 件 / 全 {len(df_active)} 件")
        render_progress_table(df_filtered)

    with tab_b:
        st.info("カンバンボードは未実装です。")

    with tab_c:
        st.info("残見込みTreemapは未実装です。")
