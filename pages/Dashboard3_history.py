import colorsys
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
        c1.metric("直間比率", "-")
        c2.metric("平均日次工数", "0 h/日")
        c3.metric("会議比率", "-")
        c4.metric("議論比率", "-")
        return

    src = df if include_mtg and include_dsc else df[df["区分"].isin(["作業"] if not include_mtg and not include_dsc else ["作業", "会議"] if include_mtg else ["作業", "議論"])]

    # 直間比率算出
    total_minutes = src["作業時間(分)"].sum()
    indirect_minutes = src[src["プロジェクト略称"] == "間接"]["作業時間(分)"].sum()
    direct_minutes = total_minutes - indirect_minutes
    direct_indirect_ratio = (direct_minutes / total_minutes * 100) if total_minutes > 0 else 0

    # 平均日次工数算出
    day_count = src["ファイル日付"].nunique() if "ファイル日付" in src.columns else 1
    avg_daily_minutes = total_minutes / day_count if day_count > 0 else 0

    # 会議・議論の工数と比率算出
    mtg_minutes = df[df["区分"] == "会議"]["作業時間(分)"].sum() if include_mtg else 0
    dsc_minutes = df[df["区分"] == "議論"]["作業時間(分)"].sum() if include_dsc else 0
    mtg_ratio = (mtg_minutes / total_minutes * 100) if total_minutes > 0 else 0
    dsc_ratio = (dsc_minutes / total_minutes * 100) if total_minutes > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("直間比率", f"{direct_indirect_ratio:.1f} %")
    c2.metric("平均日次工数", f"{avg_daily_minutes/60:.1f} h/日")
    c3.metric("会議比率", f"{mtg_ratio:.1f} %")
    c4.metric("議論比率", f"{dsc_ratio:.1f} %")

    return


_KUBUN_ORDER = ["作業", "会議", "議論"]
_PATTERN_SHAPE_MAP = {"作業": "", "会議": "/", "議論": "."}


def _generate_order_colors(order_sort: list[str]) -> dict[str, str]:
    """黄金比を使ってオーダごとに色相が均等分散した色を生成する

    Args:
        order_sort (list[str]): オーダ略称の順序リスト

    Returns:
        dict[str, str]: オーダ略称をキー、16進数カラーコードを値とする辞書
    """
    golden_ratio_conjugate = 0.618033988749895
    result = {}
    for i, order in enumerate(order_sort):
        hue = (i * golden_ratio_conjugate) % 1.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.50, 0.65)
        result[order] = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    return result


def _enrich_monthly_df(monthly_df: pd.DataFrame, order_df: pd.DataFrame) -> pd.DataFrame:
    """monthly_dfにPJ略とラベル（PJ略 オーダ略称）列を追加して返す"""
    df = monthly_df.merge(order_df, on="オーダ略称", how="left")
    df["ラベル"] = df["PJ略"] + " " + df["オーダ略称"]
    return df


def _build_chart_common_kwargs(order_df: pd.DataFrame) -> dict:
    """棒グラフ・面グラフ共通のPlotlyキーワード引数を返す

    色はオーダ単位（黄金比分散）、パターンは区分単位で表現する。
    凡例テキストは「PJ略 オーダ略称」形式。

    Args:
        order_df (pd.DataFrame): ["PJ略", "オーダ略称"] 列を持つ順序付きDataFrame

    Returns:
        dict: plotly.express に渡す共通キーワード引数
    """
    label_list = [
        f"{row['PJ略']} {row['オーダ略称']}" for _, row in order_df.iterrows()
    ]
    return {
        "color": "ラベル",
        "color_discrete_map": _generate_order_colors(label_list),
        "pattern_shape": "区分",
        "pattern_shape_map": _PATTERN_SHAPE_MAP,
        "category_orders": {
            "ラベル": list(reversed(label_list)),
            "区分": _KUBUN_ORDER,
        },
    }


def render_trend_chart_absolute(monthly_df: pd.DataFrame, order_df: pd.DataFrame) -> None:
    """月次オーダ別の工数絶対値のトレンドを積み上げ棒グラフで表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
        order_df (pd.DataFrame): ["PJ略", "オーダ略称"] 列を持つ順序付きDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    enriched_df = _enrich_monthly_df(monthly_df, order_df)
    fig = px.bar(
        enriched_df.sort_values(by="年月"),
        x="年月",
        y="作業時間(h)",
        barmode="stack",
        title="月次 オーダ別工数（会議/議論/作業レイヤ）",
        **_build_chart_common_kwargs(order_df),
    )
    fig.update_layout(yaxis_title="工数 (h)", legend_title="PJ略 オーダ(区分)")
    fig.update_layout(height=500, hovermode="x unified", legend=dict(orientation="v", traceorder="reversed"))
    st.plotly_chart(fig, width="stretch")
    return


def render_trend_chart_rate(monthly_df: pd.DataFrame, order_df: pd.DataFrame) -> None:
    """月次オーダ別の工数構成比率のトレンドを積み上げ面グラフで表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
        order_df (pd.DataFrame): ["PJ略", "オーダ略称"] 列を持つ順序付きDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    enriched_df = _enrich_monthly_df(monthly_df, order_df)
    fig = px.area(
        enriched_df.sort_values(by="年月"),
        x="年月",
        y="作業時間(h)",
        groupnorm="percent",
        title="月次 オーダ配分推移（100%積み上げ）",
        **_build_chart_common_kwargs(order_df),
    )
    fig.update_layout(yaxis_title="構成比 (%)", legend_title="PJ略 オーダ(区分)")
    fig.update_layout(height=500, hovermode="x unified", legend=dict(orientation="v", traceorder="reversed"))
    st.plotly_chart(fig, width="stretch")
    return


def render_summary_table(monthly_df: pd.DataFrame, order_df: pd.DataFrame) -> None:
    """月次オーダ別区分別のピボットテーブルを表示する

    Args:
        monthly_df (pd.DataFrame): 月次データのDataFrame
        order_df (pd.DataFrame): ["PJ略", "オーダ略称"] 列を持つ順序付きDataFrame
    """
    if monthly_df.empty:
        st.info("指定期間のデータがありません。")
        return

    enriched_df = _enrich_monthly_df(monthly_df, order_df)
    pivot = enriched_df.pivot_table(
        index=["PJ略", "オーダ略称", "区分"],
        columns="年月",
        values="作業時間(h)",
        aggfunc="sum",
        fill_value=0,
    )
    # order_df に基づいて行を並べ替え
    ordered_idx = [
        (row["PJ略"], row["オーダ略称"], k)
        for _, row in order_df.iterrows()
        for k in _KUBUN_ORDER
        if (row["PJ略"], row["オーダ略称"], k) in pivot.index
    ]
    if ordered_idx:
        pivot = pivot.loc[ordered_idx]
    pivot["合計"] = pivot.sum(axis=1)

    # reset_index してPJ略・オーダ略称を通常列にし、スタイル対象にする
    pivot_display = pivot.reset_index()
    ym_cols = [c for c in pivot.columns if c != "合計"]
    num_cols = ym_cols + ["合計"]
    label_list = [
        f"{row['PJ略']} {row['オーダ略称']}" for _, row in order_df.iterrows()
    ]
    color_map_by_label = _generate_order_colors(label_list)
    abbr_to_color = {
        row["オーダ略称"]: color_map_by_label[f"{row['PJ略']} {row['オーダ略称']}"]
        for _, row in order_df.iterrows()
    }
    styled = (
        pivot_display.style
        .hide(axis="index")
        .format("{:.1f}", subset=num_cols)
        .background_gradient(cmap="YlOrRd", subset=ym_cols, axis=None)
        .map(lambda v: "background-color: white" if v == 0 else "", subset=num_cols)
        .map(
            lambda v: f"background-color: {abbr_to_color.get(v, '')}; color: white"
            if abbr_to_color.get(v) else "",
            subset=["オーダ略称"],
        )
    )
    st.dataframe(styled, width="stretch")
    return


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()
    st.markdown("#### 過去傾向・実績ダッシュボード")

    # 後でsidebar連携に修正
    period_key = st.selectbox(
        "表示期間", ["1M", "3M", "6M", "1Y"], index=2)

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
        order_df = Output_G.get_order_sort_df()
        if chart_mode == "絶対量":
            render_trend_chart_absolute(monthly_df, order_df)
        else:
            render_trend_chart_rate(monthly_df, order_df)

        render_summary_table(monthly_df, order_df)

    with tab_b:
        st.info("見込み vs 実績は未実装です。")

    with tab_c:
        st.info("デイリータスク傾向は未実装です。")

    with tab_d:
        st.info("サブタスク状態フローは未実装です。")
