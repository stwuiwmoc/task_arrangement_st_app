import os
import sys
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import st_aggrid
import streamlit as st
from streamlit_calendar import calendar

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.G_dashboard_aggregation as Output_G
import services.H_deadline_forecast as Output_H
from sidebar import task_view

# 予測レンジのキーと日数のマッピング
_HORIZON_DAYS = {"1M": 30, "3M": 90, "6M": 180}

# リスク区分ごとの配色
_RISK_COLORS = {
    "〆切超過": "#f44336",
    "危険": "#ff9800",
    "注意": "#ffeb3b",
    "余裕": "#4caf50",
}


# ------------------------------------------------------------------------------
# パラメータ入力
# ------------------------------------------------------------------------------
def render_parameter_row() -> dict:
    """予測パラメータの入力欄を表示し、入力値を辞書で返す

    Returns:
        dict: 予測レンジ・残業時間・会議控除・デイリー負荷の設定値
    """
    c1, c2= st.columns([2, 3])

    with c1:
        c11, c12= st.columns([1, 1])
        with c11:
            horizon_key = st.selectbox(
                "予測レンジ", list(_HORIZON_DAYS.keys()), index=0, key="forecast_horizon"
            )

        with c12:
            overtime_hour = st.number_input(
                "想定残業(h/日)",
                min_value=0.0,
                max_value=5.0,
                value=1.5,
                step=0.25,
                key="forecast_overtime",
            )

        today = Task_def.get_ESS_dt().date()
        horizon_days = _HORIZON_DAYS[horizon_key]

        start_date = today
        end_date = today + timedelta(days=horizon_days)

    with c2:
        include_daily = st.checkbox(
            "デイリー負荷を含む", value=True, key="forecast_include_daily"
        )

        meeting_deduction = Output_H.estimate_meeting_deduction_minutes(lookback_days=30)
        auto_deduct = st.checkbox(
            f"会議・議論を自動控除: **{meeting_deduction / 60:.1f} h/日**", value=True, key="forecast_auto_deduct"
        )
        if not auto_deduct:
            meeting_deduction = st.number_input(
                "会議控除(分/日)",
                min_value=0.0,
                max_value=480.0,
                value=0.0,
                step=15.0,
                key="forecast_manual_deduct",
            )


    return {
        "horizon_key": horizon_key,
        "overtime_hour": overtime_hour,
        "meeting_deduction": meeting_deduction,
        "include_daily": include_daily,
        "start_date": start_date,
        "end_date": end_date
    }


# ------------------------------------------------------------------------------
# KPIカード
# ------------------------------------------------------------------------------
def render_kpi_cards(risk_df: pd.DataFrame, capacity_minutes: float, today: date):
    """KPIカードを表示する

    Args:
        risk_df (pd.DataFrame): リスク判定済みの〆切ブロック DataFrame
        capacity_minutes (float): 1営業日あたりの稼働可能時間(分)
        today (date): 基準日
    """
    c1, c2, c3, c4 = st.columns(4)

    if risk_df.empty:
        c1.metric("〆切超過ブロック", "0件")
        c2.metric("危険ブロック", "0件")
        c3.metric("直近1週間の〆切", "0件")
        c4.metric("稼働可能時間", f"{capacity_minutes / 60:.1f}h/日")
        return

    one_week_later = today + timedelta(days=7)
    overdue_count = len(risk_df[risk_df["リスク区分"] == "〆切超過"])
    danger_count = len(risk_df[risk_df["リスク区分"] == "危険"])
    week_count = len(
        risk_df[(risk_df["〆切"] >= today) & (risk_df["〆切"] <= one_week_later)]
    )

    c1.metric("〆切超過ブロック", f"{overdue_count}件")
    c2.metric("危険ブロック", f"{danger_count}件")
    c3.metric("直近1週間の〆切", f"{week_count}件")
    c4.metric("稼働可能時間", f"{capacity_minutes / 60:.1f}h/日")


# ------------------------------------------------------------------------------
# Tab A: カレンダー
# ------------------------------------------------------------------------------
def render_calendar(blocks_df: pd.DataFrame, today: date):
    """streamlit-calendarで〆切・待機日カレンダーを表示する

    イベントをクリックすると、該当タスクをサイドバーの選択タスクに反映する。

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのDataFrame
        today (date): 基準日
    """
    events = Output_H.build_calendar_events(
        blocks_df,
        show_deadline=True,
        show_waiting=True,
        today=today,
    )

    calendar_options = {
        "initialDate": today.strftime("%Y-%m-%d"),
        "locale": "ja",
        "firstDay": 1,
        "weekends": False,
        "height": 640,
        "dayMaxEvents": 4,
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,listMonth",
        },
    }

    state = calendar(
        events=events,
        options=calendar_options,
        callbacks=["eventClick"],
        key="forecast_calendar",
    )

    # イベントクリック時にサイドバーの選択タスクへ反映する
    event_click = state.get("eventClick") if isinstance(state, dict) else None
    if event_click:
        props = event_click.get("event", {}).get("extendedProps", {})
        clicked_task_id = props.get("task_id")
        clicked_task_name = props.get("name")
        if clicked_task_id and clicked_task_name:
            label = f"{clicked_task_id}: {clicked_task_name}"
            if st.session_state.get("selected_task_label") != label:
                st.session_state["selected_task_label"] = label
                st.rerun()


# ------------------------------------------------------------------------------
# Tab B: 直近アラート
# ------------------------------------------------------------------------------
def render_risk_scatter(risk_df: pd.DataFrame, capacity_minutes: float):
    """必要ペースの散布図を表示する

    横軸を〆切までの残営業日数、縦軸を必要ペースとし、
    稼働可能時間の水平線を超えたブロックを危険とみなす。

    Args:
        risk_df (pd.DataFrame): リスク判定済みの〆切ブロック DataFrame
        capacity_minutes (float): 1営業日あたりの稼働可能時間(分)
    """
    if risk_df.empty:
        st.info("〆切が設定されたブロックがありません。")
        return

    fig = go.Figure()

    for risk_name, risk_group in risk_df.groupby("リスク区分"):
        fig.add_trace(
            go.Scatter(
                x=risk_group["残営業日数"],
                y=risk_group["必要ペース(h/日)"],
                mode="markers",
                name=risk_name,
                marker=dict(
                    size=risk_group["補正後残り(分)"] / 15 + 8,
                    color=_RISK_COLORS.get(risk_name, "#78909c"),
                    line=dict(width=1, color="#ffffff"),
                    sizemode="diameter",
                ),
                customdata=risk_group[
                    ["タスクID", "タスク名", "〆切サブ名", "補正後残り(分)", "〆切"]
                ].values,
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>"
                    + "タスクID: %{customdata[0]}<br>"
                    + "〆切サブ: %{customdata[2]}<br>"
                    + "〆切: %{customdata[4]}<br>"
                    + "補正後残り: %{customdata[3]} 分<br>"
                    + "必要ペース: %{y} h/日<br>"
                    + "残営業日数: %{x} 日<extra></extra>"
                ),
            )
        )

    # 稼働可能時間の水平しきい値線
    fig.add_hline(
        y=capacity_minutes / 60,
        line_dash="dash",
        line_color="#f44336",
        annotation_text=f"稼働可能 ({capacity_minutes / 60:.2f} h/日)",
        annotation_position="top right",
    )

    # 本日の縦線
    fig.add_vline(x=0, line_dash="dot", line_color="#9e9e9e")

    fig.update_layout(
        title="〆切リスク (必要ペース)",
        xaxis_title="〆切までの残営業日数(負値は超過)",
        yaxis_title="必要ペース (h/営業日)",
        height=560,
        legend_title="リスク区分",
    )

    st.plotly_chart(fig, width="stretch")
    return


def render_risk_table(risk_df: pd.DataFrame):
    """危険ブロックの一覧テーブルを表示する

    行を選択すると、該当タスクをサイドバーの選択タスクに反映する。

    Args:
        risk_df (pd.DataFrame): リスク判定済みの〆切ブロック DataFrame
    """
    if risk_df.empty:
        st.info("表示するブロックがありません。")
        return

    display_df = risk_df[
        [
            "リスク区分",
            "タスクID",
            "タスク名",
            "〆切サブ名",
            "〆切",
            "残営業日数",
            "必要ペース(h/日)",
            "補正後残り(分)",
            "構成サブ数",
            "PJ略",
            "オーダ略",
        ]
    ].copy()
    display_df["〆切"] = display_df["〆切"].apply(lambda d: d.strftime("%Y-%m-%d"))

    risk_renderer = st_aggrid.JsCode("""
    class RiskBadgeRenderer {
        init(params) {
            const val = params.value || "";
            const colorMap = {
                "〆切超過": "#f44336",
                "危険": "#ff9800",
                "注意": "#ffeb3b",
                "余裕": "#4caf50",
            };
            const c = colorMap[val] || "#9e9e9e";
            this.eGui = document.createElement('span');
            this.eGui.style.cssText = 'background:' + c + ';color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;';
            this.eGui.innerText = val;
        }
        getGui() { return this.eGui; }
    }
    """)

    gb = st_aggrid.GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    gb.configure_column("リスク区分", cellRenderer=risk_renderer, width=120, pinned="left")
    gb.configure_column("タスクID", width=140, pinned="left")
    gb.configure_column("タスク名", width=320, pinned="left")
    gb.configure_selection(selection_mode="single", use_checkbox=False)

    ret = st_aggrid.AgGrid(
        display_df,
        gridOptions=gb.build(),
        height=320,
        theme="streamlit",
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=True,
        update_on=["selectionChanged"],
        key="risk_table_aggrid",
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

        label = f"{sel_row['タスクID']}: {sel_row['タスク名']}"
        if st.session_state.get("selected_task_label") != label:
            st.session_state["selected_task_label"] = label
            st.rerun()


def render_no_deadline_blocks(blocks_df: pd.DataFrame):
    """〆切未定ブロックの一覧を表示する

    Args:
        blocks_df (pd.DataFrame): 〆切ブロックのDataFrame
    """
    no_deadline_df = blocks_df[blocks_df["〆切"].isna()]

    with st.expander(
        f"〆切未定ブロック一覧 ({len(no_deadline_df)} 件・負荷按分の対象外)"
    ):
        if no_deadline_df.empty:
            st.info("〆切未定のブロックはありません。")
            return

        display_df = no_deadline_df[
            [
                "タスクID",
                "タスク名",
                "先頭サブID",
                "先頭サブ名",
                "構成サブ数",
                "見込み残り(分)",
                "補正後残り(分)",
                "状態",
                "PJ略",
                "オーダ略",
            ]
        ].sort_values("補正後残り(分)", ascending=False)

        st.dataframe(display_df, width="stretch", hide_index=True)
    return


# ------------------------------------------------------------------------------
# Tab C: 負荷推移・What-if
# ------------------------------------------------------------------------------
def render_load_chart(
    load_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
    total_df: pd.DataFrame,
    whatif_total_df: pd.DataFrame = None,
    ):
    """日次負荷推移の積み上げ棒グラフを表示する

    Args:
        load_df (pd.DataFrame): 日次負荷のDataFrame
        capacity_df (pd.DataFrame): 稼働可能時間のDataFrame
        total_df (pd.DataFrame): 日次合計のDataFrame
        whatif_total_df (pd.DataFrame, optional): What-if適用後の日次合計DataFrame
    """
    if load_df.empty:
        st.info("負荷按分の対象となるブロックがありません。")
        return

    # レイヤごとの配色を作成する (デイリー固定・〆切超過は固定色)
    pj_layers = sorted([
        layer
        for layer in load_df["レイヤ"].unique()
        if layer not in (Output_H.KIND_DAILY, Output_H.KIND_OVERDUE)
    ])
    color_map = Output_H.generate_order_colors(pj_layers)
    color_map[Output_H.KIND_DAILY] = Output_H.COLOR_DAILY
    color_map[Output_H.KIND_OVERDUE] = Output_H.COLOR_OVERDUE

    # 積み上げ順序: デイリー固定を最下層、〆切超過を最上層にする
    layer_order = [Output_H.KIND_DAILY] + pj_layers + [Output_H.KIND_OVERDUE]

    pivot_df = load_df.pivot_table(
        index="日付", columns="レイヤ", values="負荷(分)", aggfunc="sum", fill_value=0.0
    )

    fig = go.Figure()

    for layer in layer_order:
        if layer not in pivot_df.columns:
            continue
        fig.add_trace(
            go.Bar(
                x=pivot_df.index,
                y=pivot_df[layer] / 60,
                name=layer,
                marker_color=color_map.get(layer, "#78909c"),
                hovertemplate="%{x|%Y-%m-%d}<br>" + f"{layer}: " + "%{y:.2f} h<extra></extra>",
            )
        )

    # 稼働可能時間のライン
    fig.add_trace(
        go.Scatter(
            x=capacity_df["日付"],
            y=capacity_df["稼働可能(分)"] / 60,
            mode="lines",
            name="稼働可能時間",
            line=dict(color="#212121", width=2, dash="dash"),
            hovertemplate="%{x|%Y-%m-%d}<br>稼働可能: %{y:.2f} h<extra></extra>",
        )
    )

    # What-if適用後の合計ライン
    if whatif_total_df is not None and not whatif_total_df.empty:
        fig.add_trace(
            go.Scatter(
                x=whatif_total_df["日付"],
                y=whatif_total_df["負荷(分)"] / 60,
                mode="lines+markers",
                name="What-if適用後合計",
                line=dict(color="#1565c0", width=2),
                marker=dict(size=4),
                hovertemplate="%{x|%Y-%m-%d}<br>What-if後: %{y:.2f} h<extra></extra>",
            )
        )

    # 超過日を赤帯で強調する
    exceed_dates = total_df[total_df["超過(分)"] > 0]["日付"].tolist()
    for d in exceed_dates:
        fig.add_vrect(
            x0=pd.Timestamp(d) - pd.Timedelta(hours=12),
            x1=pd.Timestamp(d) + pd.Timedelta(hours=12),
            fillcolor="#f44336",
            opacity=0.12,
            line_width=0,
            layer="below",
        )

    fig.update_layout(
        barmode="stack",
        title="日次負荷推移 (〆切までの営業日で均等按分)",
        xaxis_title="日付",
        yaxis_title="負荷(h)",
        height=560,
        hovermode="x unified",
        legend_title="レイヤ",
    )

    st.plotly_chart(fig, width="stretch")
    return


def render_load_kpi(total_df: pd.DataFrame, whatif_total_df: pd.DataFrame = None):
    """負荷推移のKPIカードを表示する

    What-if適用時は増分をdeltaとして表示する。

    Args:
        total_df (pd.DataFrame): 日次合計のDataFrame
        whatif_total_df (pd.DataFrame, optional): What-if適用後の日次合計DataFrame
    """

    def _calc_kpi(df: pd.DataFrame) -> tuple[int, float, float]:
        business_df = df[df["稼働可能(分)"] > 0]
        exceed_days = int((business_df["超過(分)"] > 0).sum())
        max_exceed_hour = (
            float(business_df["超過(分)"].max() / 60) if not business_df.empty else 0.0
        )

        if business_df.empty or business_df["稼働可能(分)"].sum() == 0:
            utilization = 0.0
        else:
            utilization = float(
                business_df["負荷(分)"].sum() / business_df["稼働可能(分)"].sum() * 100
            )

        return exceed_days, max_exceed_hour, utilization

    base_exceed, base_max, base_util = _calc_kpi(total_df)

    c1, c2, c3 = st.columns(3)

    if whatif_total_df is not None and not whatif_total_df.empty:
        wi_exceed, wi_max, wi_util = _calc_kpi(whatif_total_df)
        c1.metric(
            "超過日数", f"{wi_exceed} 日", delta=f"{wi_exceed - base_exceed:+d} 日"
        )
        c2.metric(
            "最大超過", f"{wi_max:.2f} h", delta=f"{wi_max - base_max:+.2f} h"
        )
        c3.metric(
            "平均稼働率", f"{wi_util:.1f} %", delta=f"{wi_util - base_util:+.1f} pt"
        )
    else:
        c1.metric("超過日数", f"{base_exceed} 日")
        c2.metric("最大超過", f"{base_max:.2f} h")
        c3.metric("平均稼働率", f"{base_util:.1f} %")
    return


def render_whatif_input(today: date):
    """What-ifの入力欄と追加済みリストを表示する

    Args:
        today (date): 基準日
    """
    if "whatif_items" not in st.session_state:
        st.session_state["whatif_items"] = []

    st.markdown("##### What-if: 新規サブタスクを投入した場合の負荷を試算")

    c1, c2, c3, c4, c5 = st.columns([3, 1, 1.5, 1.5, 1])

    with c1:
        new_name = st.text_input(
            "名称",
            key="whatif_name",
            label_visibility="collapsed",
            placeholder="サブタスク名",
        )

    with c2:
        new_estimated = st.number_input(
            "見込み(分)",
            min_value=15,
            max_value=6000,
            value=60,
            step=15,
            key="whatif_estimated",
            label_visibility="collapsed",
        )

    with c3:
        new_deadline = st.date_input(
            "〆切",
            value=today + timedelta(days=14),
            key="whatif_deadline",
            label_visibility="collapsed",
        )

    with c4:
        new_start = st.date_input(
            "開始日",
            value=today,
            key="whatif_start",
            label_visibility="collapsed",
        )

    with c5:
        if st.button("追加", key="whatif_add_btn", width="stretch"):
            if not new_name:
                st.warning("名称は必須です。")
            elif new_deadline < new_start:
                st.warning("〆切は開始日以降にしてください。")
            else:
                st.session_state["whatif_items"].append({
                    "名称": new_name,
                    "見込み(分)": int(new_estimated),
                    "〆切": new_deadline,
                    "開始日": new_start,
                })
                st.rerun()

    # 追加済みリストの表示と削除
    if st.session_state["whatif_items"]:
        st.caption(f"追加済み: {len(st.session_state['whatif_items'])} 件")
        for i, item in enumerate(st.session_state["whatif_items"]):
            row_c1, row_c2 = st.columns([9, 1])
            with row_c1:
                st.write(
                    f"{i + 1}). **{item['名称']}** "
                    f"見込み: {item['見込み(分)']}分 "
                    f"開始: {item['開始日'].strftime('%Y-%m-%d')} "
                    f"〆切: {item['〆切'].strftime('%Y-%m-%d')}"
                )
            with row_c2:
                if st.button("削除", key=f"whatif_del_{i}", width="stretch"):
                    st.session_state["whatif_items"].pop(i)
                    st.rerun()

        if st.button("全クリア", key="whatif_clear_btn"):
            st.session_state["whatif_items"] = []
            st.rerun()


# ------------------------------------------------------------------------------
# メイン
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    st.markdown("#### 予測・〆切ダッシュボード")
    today = Task_def.get_ESS_dt().date()

    # 予測パラメータの入力
    c1, c2= st.columns(2)
    with c1:
        params = render_parameter_row()

        # 〆切ブロックの構築
        with st.spinner("タスク情報を集計中..."):
            blocks_df = Output_H.build_deadline_blocks_df(today=today)

        if blocks_df.empty:
            st.warning("未完了サブタスクを持つActiveタスクが存在しません。")
            st.stop()

        # 稼働可能時間とリスクの算出
        capacity_minutes = Output_H.get_daily_capacity_minutes(
            today if Output_H.is_business_day(today) else today + timedelta(days=1),
            overtime_hour=params["overtime_hour"],
            meeting_deduction_minutes=params["meeting_deduction"],
        )

        risk_df = Output_H.build_risk_df(blocks_df, capacity_minutes, today=today)

    with c2:
        # KPIカード
        render_kpi_cards(risk_df, capacity_minutes, today)

    tab_a, tab_b, tab_c = st.tabs(["カレンダー", "直近アラート", "負荷推移・What-if"])

    with tab_a:
        render_calendar(blocks_df, today)

        st.markdown("##### 〆切リスク一覧 (行クリックでサイドバーに反映)")
        render_risk_table(risk_df)
        render_no_deadline_blocks(blocks_df)

    with tab_b:
        render_risk_scatter(risk_df, capacity_minutes)

    with tab_c:
        # 基準となる日次負荷を算出する
        load_df = Output_H.calculate_daily_load(
            blocks_df, params["start_date"], params["end_date"], today=today
        )

        daily_fixed_df = pd.DataFrame()
        if params["include_daily"]:
            daily_fixed_df = Output_H.build_daily_fixed_load(params["start_date"], params["end_date"])

            if not daily_fixed_df.empty:
                load_df = pd.concat([load_df, daily_fixed_df], ignore_index=True)

        capacity_df = Output_H.build_capacity_df(
            params["start_date"],
            params["end_date"],
            overtime_hour=params["overtime_hour"],
            meeting_deduction_minutes=params["meeting_deduction"],
        )

        total_df = Output_H.summarize_daily_total(load_df, capacity_df)

        # What-if適用後の日次負荷を算出する
        whatif_items = st.session_state.get("whatif_items", [])
        whatif_total_df = None

        if whatif_items:
            whatif_blocks_df = Output_H.build_whatif_blocks_df(
                whatif_items, today=today
            )
            combined_blocks_df = pd.concat(
                [blocks_df, whatif_blocks_df], ignore_index=True
            )
            whatif_load_df = Output_H.calculate_daily_load(
                combined_blocks_df, params["start_date"], params["end_date"], today=today
            )

            if not daily_fixed_df.empty:
                whatif_load_df = pd.concat(
                    [whatif_load_df, daily_fixed_df], ignore_index=True
                )

            whatif_total_df = Output_H.summarize_daily_total(
                whatif_load_df, capacity_df
            )

        render_load_chart(load_df, capacity_df, total_df, whatif_total_df)
        render_load_kpi(total_df, whatif_total_df)
        st.markdown("---")
        render_whatif_input(today)