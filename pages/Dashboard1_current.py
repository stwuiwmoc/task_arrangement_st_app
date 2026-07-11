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


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()
    st.markdown("#### 現状ダッシュボード")

    # Activeタスクの横断集計を取得
    active_task_summary_df = Output_G.build_active_task_summary_df()

    if active_task_summary_df.empty:
        st.warning("Activeタスクが存在しません。")
        st.stop()

    # KPIカードを表示
    render_kpi_cards(active_task_summary_df)

    # フィルタを表示
    df_filtered = render_filters(active_task_summary_df)