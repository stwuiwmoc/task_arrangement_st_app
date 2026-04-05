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
        st.markdown("#### 工数実績csv生データ表示（降順）")

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
        df_break = Output_E.extract_rest_time_from_WorkLog(WorkLog_filepath)
        df_sum_subtask_withMTG = Output_E.sum_df_each_subtask(WorkLog_filepath, include_MTG=True)
        df_sum_subtask_withoutMTG = Output_E.sum_df_each_subtask(WorkLog_filepath, include_MTG=False)
        df_sum_order_withMTG = Output_E.sum_df_each_order(df_sum_subtask_withMTG)
        df_sum_order_withoutMTG = Output_E.sum_df_each_order(df_sum_subtask_withoutMTG)
        summary_df = Output_E.calc_WorkLog_summary(WorkLog_filepath, df_sum_order_withMTG, add_daytime_break)

        # 表示
        # インデックスで降順ソートして表示
        st.data_editor(
            pd.read_csv(WorkLog_filepath, parse_dates=['開始時刻', '終了時刻']).sort_index(ascending=False),
            width="stretch")

        fig = Output_E.make_WorkLog_barchart(WorkLog_filepath)
        if fig is not None:
            st.pyplot(fig)

        st.markdown("#### ESS登録用出力")
        st.data_editor(summary_df, width="stretch", hide_index=True)
        st.data_editor(df_break, width="stretch", hide_index=True)

        st.markdown("#### BJP登録用出力")
        st.table(Output_E.convert_df_for_display(df_sum_order_withMTG))

        st.markdown("#### サブタスク別集計")
        st.data_editor(
            df_sum_subtask_withMTG, width="stretch")

        st.markdown("#### 朝会報告用（MTG除外）")
        st.table(Output_E.convert_df_for_display(df_sum_order_withoutMTG))

        st.markdown("#### Will-doリスト実績表示")

        willdo_dir = os.path.join("data", "WillDo")
        willdo_file = os.path.join(willdo_dir, f"WillDo{selected_str}.csv")

        if os.path.exists(willdo_file):
            df_past = pd.read_csv(willdo_file, encoding="utf-8-sig")
            st.data_editor(
                df_past,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Will-doリスト未作成です")


    else:
        st.info("工数実績csv未作成です")
