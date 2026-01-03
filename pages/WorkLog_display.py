import os
import sys

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import services.B_WillDo_create as Output_B
import services.E_WorkLog_formatting as Output_E
from sidebar import task_view

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    col_left, col_center, col_right = st.columns([2, 1, 1])
    with col_left:
        st.markdown("#### ESS/BJP入力用処理")

    with col_center:
        add_daytime_break = st.checkbox("昼休憩を考慮", value=True)

    with col_right:
        selected_date = st.date_input(
            "日付を選択してください",
            value=Output_B.get_without_today_latest_WillDO_date(),
            key="willdo_date_input",
            label_visibility="collapsed"
        )

    selected_str = selected_date.strftime("%y%m%d")
    WorkLog_filepath = os.path.join("data", "WorkLogs", f"工数実績{selected_str}.csv")

    if os.path.exists(WorkLog_filepath):
        # データ処理
        df_sum_subtask = Output_E.sum_df_each_subtask(WorkLog_filepath)
        df_sum_order = Output_E.sum_df_each_order(df_sum_subtask)
        df_display = Output_E.convert_df_for_display(df_sum_order)
        summary_df = Output_E.calc_WorkLog_summary(WorkLog_filepath, df_sum_order, add_daytime_break)

        # 表示
        st.data_editor(summary_df, use_container_width=True, hide_index=True)
        st.table(df_display)

        st.markdown("#### サブタスク別集計")
        st.data_editor(
            df_sum_subtask, use_container_width=True)
    else:
        st.info("will-doリスト未作成です（＝工数実績csvも未作成）")
