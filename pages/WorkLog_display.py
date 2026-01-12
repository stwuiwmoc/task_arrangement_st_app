import datetime
import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import services.E_WorkLog_formatting as Output_E
from sidebar import task_view

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    col_left, col_center, col_right = st.columns([2, 1, 1])
    with col_left:
        st.markdown("#### ESS登録用出力")

    with col_center:
        add_daytime_break = st.checkbox("昼休憩を考慮", value=True)

    with col_right:
        selected_date = st.date_input(
            "日付を選択してください",
            value=datetime.date.today(),
            key="willdo_date_input",
            label_visibility="collapsed"
        )

    selected_str = selected_date.strftime("%y%m%d")
    WorkLog_filepath = os.path.join("data", "WorkLogs", f"工数実績{selected_str}.csv")

    if os.path.exists(WorkLog_filepath):
        # データ処理
        df_sum_subtask_withMTG = Output_E.sum_df_each_subtask(WorkLog_filepath, include_MTG=True)
        df_sum_subtask_withoutMTG = Output_E.sum_df_each_subtask(WorkLog_filepath, include_MTG=False)
        df_sum_order_withMTG = Output_E.sum_df_each_order(df_sum_subtask_withMTG)
        df_sum_order_withoutMTG = Output_E.sum_df_each_order(df_sum_subtask_withoutMTG)
        summary_df = Output_E.calc_WorkLog_summary(WorkLog_filepath, df_sum_order_withMTG, add_daytime_break)

        # 表示
        st.data_editor(summary_df, use_container_width=True, hide_index=True)
        fig = Output_E.make_WorkLog_barchart(WorkLog_filepath)
        if fig is not None:
            st.pyplot(fig)
        st.markdown("工数実績csv生データ")
        st.data_editor(
            pd.read_csv(WorkLog_filepath, parse_dates=['開始時刻', '終了時刻']),
            use_container_width=True)

        st.markdown("#### BJP登録用出力")
        st.table(Output_E.convert_df_for_display(df_sum_order_withMTG))

        st.markdown("#### サブタスク別集計")
        st.data_editor(
            df_sum_subtask_withMTG, use_container_width=True)

        st.markdown("#### 朝会報告用（MTG除外）")
        st.table(Output_E.convert_df_for_display(df_sum_order_withoutMTG))

    else:
        st.info("工数実績csv未作成です")
