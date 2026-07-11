import os
import sys
from datetime import datetime

import pandas as pd
import st_aggrid
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.G_dashboard_aggregation as Output_G
from sidebar import task_view

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()
    st.markdown("#### 過去傾向・実績ダッシュボード")

    tab_a, tab_b, tab_c, tab_d = st.tabs([
        "工数トレンド",
        "見込み vs 実績（未実装）",
        "デイリータスク傾向（未実装）",
        "サブタスク状態フロー（未実装）"
    ])

    with tab_a:
        pass

    with tab_b:
        st.info("見込み vs 実績は未実装です。")

    with tab_c:
        st.info("デイリータスク傾向は未実装です。")

    with tab_d:
        st.info("サブタスク状態フローは未実装です。")
