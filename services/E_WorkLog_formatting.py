# %%
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models.Task_definition as Task_def


def sum_df_each_subtask(csv_filepath: str) -> pd.DataFrame:

    # 1. CSVファイルの全ての行・列をdataframeとして読み込む
    # ※開始時刻列、終了時刻列はdatetime型として読み込む
    df = pd.read_csv(csv_filepath, parse_dates=['開始時刻', '終了時刻'])
    # 2. 終了時刻列と開始時刻列の差分を計算し、時間列（分）を追加する
    df['実時間'] = (df['終了時刻'] - df['開始時刻']).dt.total_seconds() / 60
    # 3. 終了時刻列と開始時刻列を削除
    df = df.drop(columns=['開始時刻', '終了時刻'])

    # 4. 列結合と削除
    # 4-1. タスクID列・サブタスクID列を結合し、新しい列「ID」列を作成する
    # ※ 結合ルール : タスクID + サブタスクID
    df['ID'] = df['タスクID'].astype(str) + df['サブタスクID'].astype(str)

    # 4-2. タスク名列・サブタスク名列を結合し、新しい列「名前」列を作成する
    # ※ 結合ルール : タスク名 + " / " + サブタスク名
    df['名前'] = df['タスク名'].astype(str) + " / " + df['サブタスク名'].astype(str)
    # 4-3. タスクID列・サブタスクID列・タスク名列・サブタスク名列を削除する
    df = df.drop(columns=['タスクID', 'サブタスクID', 'タスク名', 'サブタスク名'])

    # 5. ID列が同じ行をグループ化し、時間列を合計する
    # ※ 時間列のみ集計し、他の列は最初の行の値を使用する
    df_sum = df.groupby('ID', as_index=False).agg({
        '名前': 'first',
        '実時間': 'sum',
        'オーダ番号': 'first',
        'オーダ略称': 'first',
        'プロジェクト略称': 'first',
    })
    # 6. 「プロジェクト略称」列の列名を「PJ略」に変更する
    df_sum = df_sum.rename(columns={'プロジェクト略称': 'PJ略'})

    return df_sum

def sum_df_each_order(
        df_sum_subtask: pd.DataFrame) -> pd.DataFrame:

    # 1. 時間列で降順ソート
    df = df_sum_subtask.copy()
    df = df.sort_values(by='実時間', ascending=False)

    # 2. df全体をオーダ番号列でソート
    # ※ソート順は、OrderInformation().df["order_number"]の順番に従う
    order_info = Task_def.OrderInformation()
    order_number_index = {num: i for i, num in enumerate(order_info.df["order_number"]) }
    df_sum_subtask_sorted = df.sort_values(
        by=['実時間'],
        ascending=[False],
    )

    # 3. オーダ番号列が同じ行をグループ化し、時間列を合計する
    # ※ 時間列は集計、名前列は結合、他の列は最初の行の値を使用する
    df_sum_order = df_sum_subtask_sorted.groupby('オーダ番号', as_index=False).agg({
        '実時間': 'sum',
        '名前': lambda x: '  \n'.join(x),
    })

    # 4. 時間列をint型に変換
    df_sum_order['実時間'] = df_sum_order['実時間'].astype(int)

    # 5. 時間列を15分単位で切り捨てた「工数」列を作成
    df_truncated = df_sum_order.copy()
    df_truncated['工数'] = (df_truncated['実時間'] // 15) * 15

    # 6. オーダ番号列で再度ソート
    # ※ソート順は、OrderInformation().df["order_number"]の順番に従う
    df_truncated_sorted = df_truncated.sort_values(
        by=['オーダ番号'],
        ascending=[True],
        key=lambda col: col.map(order_number_index) if col.name == 'オーダ番号' else col
    )
    return df_truncated_sorted


def convert_df_for_display(
        df: pd.DataFrame) -> pd.DataFrame:

    # 1. 時間列と工数列を、分数から時間表記に変換
    # ※ 例: 67 -> "1h07m"
    df_display = df.copy()
    df_display['実時間'] = df_display['実時間'].apply(_format_minutes_to_hours_minutes)
    df_display['工数'] = df_display['工数'].apply(_format_minutes_to_hours_minutes)

    # 2. 列の並び順を変更
    df_display = df_display[['オーダ番号', '工数', '実時間', '名前']]

    return df_display


def calc_WorkLog_summary(csv_filepath: str, df_truncated: pd.DataFrame, add_daytime_break: bool) -> pd.DataFrame:
    # 1. CSVファイルの全ての行・列をdataframeとして読み込む
    # ※開始時刻列、終了時刻列はdatetime型として読み込む
    df = pd.read_csv(csv_filepath, parse_dates=['開始時刻', '終了時刻'])

    # 2. 開始時刻で最も早い行のdatetimeと、終了時刻で最も遅い行のdatetimeを取得
    earliest_start = df['開始時刻'].min()
    latest_end = df['終了時刻'].max()

    # 3. 滞在時間を計算
    total_stay_minutes = int((latest_end - earliest_start).total_seconds() / 60)

    # 4. dfから実時間合計と工数合計を取得して実働時間の15分切り捨てを計算
    total_real_minutes = df_truncated['実時間'].sum()
    total_work_minutes = df_truncated['工数'].sum()
    total_real_minutes_truncated = (total_real_minutes // 15) * 15
    others_minutes = total_real_minutes_truncated - total_work_minutes


    # 5. 昼休憩を除く休憩時間を計算
    if add_daytime_break:
        daytime_break_minutes = 60
    else:
        daytime_break_minutes = 0
    total_break_minutes = total_stay_minutes - total_real_minutes - daytime_break_minutes

    # 6. 表示用のdfを作成
    # 6-1. 各種時間をフォーマット変換して辞書に格納
    output_dict = {
        "ESS始業": earliest_start.strftime("%H:%M"),
        "ESS終業": latest_end.strftime("%H:%M"),
        "ESS滞在": _format_minutes_to_hours_minutes(total_stay_minutes),
        "ESS休憩": _format_minutes_to_hours_minutes(total_break_minutes),
        "ESS実働": _format_minutes_to_hours_minutes(total_real_minutes),
        "BJP合計": _format_minutes_to_hours_minutes(total_real_minutes_truncated),
        "BJPその他": _format_minutes_to_hours_minutes(others_minutes),
    }

    # 6-2. 辞書のkeysを列名、valuesをデータとしてDataFrameを作成
    df_output = pd.DataFrame([output_dict])

    return df_output


def make_WorkLog_barchart(csv_filepath: str):
    # 1. CSVファイルの全ての行・列をdataframeとして読み込む
    # ※開始時刻列、終了時刻列はdatetime型として読み込む
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    df = pd.read_csv(csv_filepath, parse_dates=['開始時刻', '終了時刻'])

    # 2. 全タスクを1本の横棒（同じy位置）にbroken_barhで描画
    df['タスク表示名'] = df['タスク名'].astype(str) + ' / ' + df['サブタスク名'].astype(str)

    # 5時～13時、13時～21時、21時～翌5時の3分割
    def _get_time_range3(dt):
        t = dt.time()
        if t >= datetime.strptime('05:00', '%H:%M').time() and t < datetime.strptime('13:00', '%H:%M').time():
            return 'morning'
        elif t >= datetime.strptime('13:00', '%H:%M').time() and t < datetime.strptime('21:00', '%H:%M').time():
            return 'afternoon'
        else:
            return 'night'

    df['時間帯'] = df['開始時刻'].apply(_get_time_range3)
    df_morning = df[df['時間帯'] == 'morning']
    df_afternoon = df[df['時間帯'] == 'afternoon']
    df_night = df[df['時間帯'] == 'night']

    fig, axes = plt.subplots(3, 1, figsize=(15, 2), sharex=False)

    # fig全体で色を一意に割り当てる
    all_indices = df.index.tolist()
    cmap = plt.cm.get_cmap('Set1', max(1, len(all_indices)))

    def _draw_timeband(ax, df_band, start_time, end_time, hour_range):
        barh_data = []
        color_list = []
        for _, row in df_band.iterrows():
            start = mdates.date2num(row['開始時刻'])
            duration = (row['終了時刻'] - row['開始時刻']).total_seconds() / 86400
            barh_data.append((start, duration))
            # 全体dfのindexを使って色を割り当て
            color_list.append(cmap(row.name))
        if barh_data:
            ax.broken_barh(barh_data, (0.7, 0.4), facecolors=color_list)
        ax.set_yticks([])
        ax.set_yticklabels([])
        if hour_range is not None:
            ax.xaxis.set_major_locator(mdates.HourLocator(byhour=hour_range, interval=1))
        else:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.grid(True, which='major', linestyle='solid', color='gray', linewidth=1)
        ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
        ax.xaxis.grid(True, which='minor', linestyle='dotted', color='gray', linewidth=0.8)
        ax.set_xlim(mdates.date2num(start_time), mdates.date2num(end_time))

    # 5:00～13:00
    morning_start = datetime.combine(df['開始時刻'].min().date(), datetime.strptime('05:00', '%H:%M').time())
    morning_end = datetime.combine(df['開始時刻'].min().date(), datetime.strptime('13:00', '%H:%M').time())
    _draw_timeband(axes[0], df_morning, morning_start, morning_end, range(5,14))

    # 13:00～21:00
    afternoon_start = datetime.combine(df['開始時刻'].min().date(), datetime.strptime('13:00', '%H:%M').time())
    afternoon_end = datetime.combine(df['開始時刻'].min().date(), datetime.strptime('21:00', '%H:%M').time())
    _draw_timeband(axes[1], df_afternoon, afternoon_start, afternoon_end, range(13,22))

    # 21:00～翌5:00
    night_start = datetime.combine(df['開始時刻'].min().date(), datetime.strptime('21:00', '%H:%M').time())
    next_day = df['開始時刻'].min().date() + timedelta(days=1)
    night_end = datetime.combine(next_day, datetime.strptime('05:00', '%H:%M').time())
    _draw_timeband(axes[2], df_night, night_start, night_end, None)

    fig.tight_layout()
    return fig



def _format_minutes_to_hours_minutes(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h{mins:02d}m"


if __name__ == "__main__":
    pass