import os
import sys
from datetime import datetime

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.E_WorkLog_formatting as Output_E
from sidebar import task_view

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    # データ処理
    worklog_date = datetime(2026, 1, 2).date()
    df_sum_subtask = Output_E.sum_df_each_subtask(worklog_date)
    df_sum_order = Output_E.sum_df_each_order(df_sum_subtask)
    df_display = Output_E.convert_df_for_display(df_sum_order)

    # 表示
    st.markdown("#### オーダ別集計（切り捨て後）")
    st.table(df_display)

    st.markdown("#### サブタスク別集計")
    st.data_editor(
        df_sum_subtask, use_container_width=True)
