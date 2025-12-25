import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def
import services.A_task_identify as Output_A
from sidebar import task_view

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    task_view.task_sidebar()

    # ファイルアップロード
    st.markdown("#### OneNote同期用ファイルアップロード")
    uploaded_file = st.file_uploader("ファイルアップロード", type=["txt"], label_visibility="collapsed")
    if uploaded_file is not None:
        # ファイルを保存（上書き）
        save_path = os.path.join("data", "onenote_output.txt")
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"ファイルを {save_path} に保存しました。")

    st.markdown("#### OneNote同期判定")

    df = Output_A.task_identify_first_half()
    # st.dataframe(df, use_container_width=True)  # デバッグ用表示

    # 編集画面用に表示する行・列のみフィルタ
    if df.empty:
        st.info("全て同期済")
    else:
        confirm_rows = df["action_type"].isin(["update_subtask_field", "update_waiting_date", "create_task", "update_task_name"])
        confirm_cols = ["confirm_text", "csv", "onenote", "update_csv", "order_number"]
        auto_cols = ["confirm_text", "update_csv"]

        # 要確認・自動反映のdfを分割
        df_confirm = df.loc[confirm_rows, confirm_cols].copy()
        df_auto = df.loc[~confirm_rows, auto_cols].copy()

        # 自動反映dfの表示
        st.markdown("自動反映予定の項目")
        df_auto["update_csv"] = df_auto["update_csv"].astype(bool)
        edited_df_auto = st.data_editor(df_auto, use_container_width=True)

        # 要確認dfの編集
        st.markdown("反映有無の確認が必要な項目")
        df_confirm["update_csv"] = df_confirm["update_csv"].astype(bool)
        edited_df_confirm = st.data_editor(df_confirm, use_container_width=True)

        # 編集後の2つのdfから全行・全列そろった編集後のdfを作成
        edited_df = df.copy()
        # 要確認部分を反映
        edited_df.loc[confirm_rows, confirm_cols] = edited_df_confirm
        # 自動反映部分はupdate_csv列だけ反映（他列は元のまま）
        edited_df.loc[~confirm_rows, auto_cols] = edited_df_auto

        # st.dataframe(edited_df, use_container_width=True) # デバッグ用表示

        # 確認済みの更新内容を反映（ボタンで実行）
        if st.button("反映内容を確定してCSVに反映", key="onenote_sync_apply"):
            Output_A.task_identify_second_half(edited_df)
            st.success("反映が完了しました。")

    # オーダ管理csvの表示
    st.markdown("#### オーダ番号コピペ用")
    order_info = Task_def.OrderInformation()
    st.dataframe(order_info.df, use_container_width=True)