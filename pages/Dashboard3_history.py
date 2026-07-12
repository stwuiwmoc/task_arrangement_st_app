import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.G_dashboard_aggregation as Output_G
from sidebar import task_view


def render_kpi_cards(df: pd.DataFrame, include_mtg: bool, include_dsc: bool):
    """KPIカードを表示する

    Args:
        df (pd.DataFrame): 工数実績の集計後DataFrame
        include_mtg (bool): 会議(MTG)を含めるかどうか
        include_dsc (bool): 議論(DSC)を含めるかどうか
    """
    if df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("期間内総工数", "0 h")
        c2.metric("平均日次工数", "0 h/日")
        c3.metric("会議比率", "-")
        c4.metric("議論比率", "-")
        return

    src = df if include_mtg and include_dsc else df[df["区分"].isin(["作業"] if not include_mtg and not include_dsc else ["作業", "会議"] if include_mtg else ["作業", "議論"])]
    total_minutes = src["作業時間(分)"].sum()
    day_count = src["ファイル日付"].nunique() if "ファイル日付" in src.columns else 1
    avg_daily_minutes = total_minutes / day_count if day_count > 0 else 0

    mtg_minutes = df[df["区分"] == "会議"]["作業時間(分)"].sum() if include_mtg else 0
    dsc_minutes = df[df["区分"] == "議論"]["作業時間(分)"].sum() if include_dsc else 0
    mtg_ratio = (mtg_minutes / total_minutes * 100) if total_minutes > 0 else 0
    dsc_ratio = (dsc_minutes / total_minutes * 100) if total_minutes > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("期間内総工数", f"{total_minutes/60:.1f} h")
    c2.metric("平均日次工数", f"{avg_daily_minutes/60:.1f} h/日")
    c3.metric("会議比率", f"{mtg_ratio:.1f} %")
    c4.metric("議論比率", f"{dsc_ratio:.1f} %")

    return


def render_trend_chart_absolute(monthly_df: pd.DataFrame) -> None:
    """月次オーダ別の工数絶対値のトレンドを積み上げ棒グラフで表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    plot_df = monthly_df.copy()
    plot_df["ラベル"] = plot_df["オーダ略称"] + "(" + plot_df["区分"] + ")"

    fig = px.bar(
        plot_df.sort_values(by="年月"),
        x="年月",
        y="作業時間(h)",
        color="ラベル",
        barmode="stack",
        title="月次 オーダ別工数（会議/議論/作業レイヤ）",
        pattern_shape="区分",
        pattern_shape_map={"作業": "", "会議": "/", "議論": "."},
    )
    fig.update_layout(yaxis_title="工数 (h)", legend_title="オーダ(区分)")

    fig.update_layout(height=500, hovermode="x unified", legend=dict(orientation="v"))
    st.plotly_chart(fig, width="stretch")
    return


def render_trend_chart_rate(monthly_df: pd.DataFrame) -> None:
    """月次オーダ別の工数構成比率のトレンドを積み上げ面グラフで表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    plot_df = monthly_df.copy()
    plot_df["ラベル"] = plot_df["オーダ略称"] + "(" + plot_df["区分"] + ")"

    fig = px.area(
        plot_df.sort_values(by="年月"),
        x="年月",
        y="作業時間(h)",
        color="ラベル",
        groupnorm="percent",
        title="月次 オーダ配分推移（100%積み上げ）",
    )
    fig.update_layout(yaxis_title="構成比 (%)", legend_title="オーダ(区分)")

    fig.update_layout(height=500, hovermode="x unified", legend=dict(orientation="v"))
    st.plotly_chart(fig, width="stretch")
    return


def render_summary_table(monthly_df: pd.DataFrame) -> None:
    """月次オーダ別区分別のピボットテーブルを表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    pivot = monthly_df.pivot_table(
        index="年月",
        columns=["オーダ略称", "区分"],
        values="作業時間(h)",
        aggfunc="sum",
        fill_value=0,
    )
    pivot["月合計"] = pivot.sum(axis=1)
    data_cols = [c for c in pivot.columns if c[0] != "月合計"]
    styled = (
        pivot.style
        .format("{:.1f}")
        .background_gradient(cmap="YlOrRd", subset=data_cols, axis=None)
        .map(lambda v: "background-color: white" if v == 0 else ""))
    st.dataframe(styled, width="stretch")
    return


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()
    st.markdown("#### 過去傾向・実績ダッシュボード")

    # 後でsidebar連携に修正
    period_key = st.selectbox(
        "表示期間",["1M", "3M", "6M", "1Y"])

    start_date, end_date = Output_G.get_period_range(period_key)

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        st.caption(
            f"対象期間：**{start_date.strftime('%Y/%m/%d')}** 〜"
            f" **{end_date.strftime('%Y/%m/%d')}**"
            f"（サイドバーの期間クイック選択で変更可能）"
        )

    with c2:
        include_mtg = st.checkbox("会議(MTG)を含める", value=True, key="include_mtg_history")
    with c3:
        include_dsc = st.checkbox("議論(DSC)を含める", value=True, key="include_dsc_history")

    # データ読み込み
    with st.spinner("データを読み込み中..."):
        worklog_df = Output_G.load_worklogs_in_period(start_date, end_date)

    # KPI
    render_kpi_cards(worklog_df, include_mtg, include_dsc)
    st.markdown("---")



    tab_a, tab_b, tab_c, tab_d = st.tabs([
        "工数トレンド",
        "見込み vs 実績（未実装）",
        "デイリータスク傾向（未実装）",
        "サブタスク状態フロー（未実装）"
    ])

    with tab_a:
        chart_mode = st.radio("表示モード", ["絶対量", "構成比"], horizontal=True, key="chart_mode_history")
        monthly_df = Output_G.aggregate_monthly_by_order(worklog_df, include_mtg, include_dsc)
        if chart_mode == "絶対量":
            render_trend_chart_absolute(monthly_df)
        else:
            render_trend_chart_rate(monthly_df)

        render_summary_table(monthly_df)

    with tab_b:
        st.info("見込み vs 実績は未実装です。")

    with tab_c:
        st.info("デイリータスク傾向は未実装です。")

    with tab_d:
        st.info("サブタスク状態フローは未実装です。")
