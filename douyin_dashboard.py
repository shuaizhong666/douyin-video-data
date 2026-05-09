"""
抖音视频数据可视化看板（GitHub Raw 版）
数据文件每日自动同步至 GitHub，本应用从 raw URL 读取
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import warnings
from datetime import date
import requests
from io import BytesIO

warnings.filterwarnings('ignore')

st.set_page_config(page_title="抖音视频数据分析看板", page_icon="🎵", layout="wide", initial_sidebar_state="expanded")

# ======================== 远程数据 URL（请替换为你的实际 raw 链接） ========================
DATA_URL = "https://raw.githubusercontent.com/shuaizhong666/抖音视频看板/main/抖音视频数据汇总.xlsx"

@st.cache_data(ttl=3600)
def load_data_from_url(url):
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_excel(BytesIO(resp.content), engine='openpyxl')
        return df
    except Exception as e:
        st.error(f"读取远程数据失败: {e}\n请确认文件已上传至仓库且 raw URL 正确。")
        return pd.DataFrame()

def preprocess_for_analysis(df):
    if df.empty:
        return df
    df_work = df.copy()
    num_cols = ['点赞数', '评论数', '分享数', '收藏数', '粉丝数', '获赞总数']
    for col in num_cols:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce')
    if '创建时间' in df_work.columns:
        df_work['publish_date'] = pd.to_datetime(df_work['创建时间'], errors='coerce')
    return df_work

def get_author_aggregation(df):
    if df.empty or '作者昵称' not in df.columns:
        return pd.DataFrame()
    agg_dict = {'视频ID': 'count'}
    for col in ['点赞数', '评论数', '收藏数']:
        if col in df.columns:
            agg_dict[col] = 'sum'
    author_stats = df.groupby('作者昵称').agg(agg_dict).reset_index()
    author_stats.rename(columns={'视频ID': '发布数量'}, inplace=True)
    if '点赞数' in df.columns:
        author_stats.rename(columns={'点赞数': '总点赞数'}, inplace=True)
    if '评论数' in df.columns:
        author_stats.rename(columns={'评论数': '总评论数'}, inplace=True)
    if '收藏数' in df.columns:
        author_stats.rename(columns={'收藏数': '总收藏数'}, inplace=True)
    if '粉丝数' in df.columns:
        fans = df.groupby('作者昵称')['粉丝数'].max().reset_index()
        author_stats = author_stats.merge(fans, on='作者昵称', how='left')
    else:
        author_stats['粉丝数'] = None
    return author_stats

def main():
    st.title("🎵 抖音视频数据可视化看板")
    st.markdown("**数据来源**：GitHub 仓库（每日自动同步）")

    raw_df = load_data_from_url(DATA_URL)
    if raw_df.empty:
        st.stop()

    df_ana = preprocess_for_analysis(raw_df)

    # ========== 侧边栏全局筛选 ==========
    st.sidebar.header("🔍 全局数据筛选")
    st.sidebar.markdown(f"**原始视频数**: {len(df_ana)}")
    filter_mask = pd.Series([True] * len(df_ana))

    if 'publish_date' in df_ana.columns:
        valid_dates = df_ana['publish_date'].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().date()
            max_data_date = valid_dates.max().date()
            date_range = st.sidebar.date_input("选择日期范围", value=(min_date, max_data_date), min_value=min_date)
            if isinstance(date_range, (date, pd.Timestamp)):
                start_date = end_date = date_range
            else:
                start_date, end_date = date_range
            mask = (df_ana['publish_date'].dt.date >= start_date) & (df_ana['publish_date'].dt.date <= end_date)
            filter_mask &= mask
            st.sidebar.info(f"筛选后视频数: {filter_mask.sum()}")

    for col_cn in ['点赞数', '评论数', '分享数', '收藏数']:
        if col_cn in df_ana.columns and not df_ana[col_cn].isna().all():
            min_val = float(df_ana[col_cn].min())
            max_val = float(df_ana[col_cn].max())
            if min_val < max_val:
                selected = st.sidebar.slider(f"{col_cn} 范围", min_val, max_val, (min_val, max_val))
                mask = (df_ana[col_cn] >= selected[0]) & (df_ana[col_cn] <= selected[1])
                filter_mask &= mask

    df_filtered = df_ana[filter_mask].copy()
    raw_filtered = raw_df.loc[filter_mask] if filter_mask.dtype == bool else raw_df.iloc[filter_mask]

    # 作者双榜
    st.subheader("👥 作者维度综合排行榜")
    author_df = get_author_aggregation(df_filtered)
    if not author_df.empty:
        tab1, tab2 = st.tabs(["📦 发布数量 Top10", "❤️ 总点赞数 Top10"])
        with tab1:
            top_publish = author_df.sort_values('发布数量', ascending=False).head(10)
            st.dataframe(top_publish, use_container_width=True)
            fig_pub = px.bar(top_publish, x='作者昵称', y='发布数量', title="发布数量 Top10 作者", text_auto=True, color='发布数量')
            st.plotly_chart(fig_pub, use_container_width=True)
        with tab2:
            if '总点赞数' in author_df.columns:
                top_likes = author_df.sort_values('总点赞数', ascending=False).head(10)
                st.dataframe(top_likes, use_container_width=True)
                fig_likes = px.bar(top_likes, x='作者昵称', y='总点赞数', title="总点赞数 Top10 作者", text_auto=True, color='总点赞数')
                st.plotly_chart(fig_likes, use_container_width=True)
            else:
                st.info("数据中不含点赞数，无法展示点赞榜。")
    else:
        st.info("未找到作者昵称列，无法进行作者排行榜分析。")

    # 单日发布监控
    st.subheader("🔍 单日发布监控（支持筛选未发布作者）")
    if '创建时间' in raw_df.columns and '作者昵称' in raw_df.columns:
        raw_df_date = raw_df.copy()
        raw_df_date['publish_date'] = pd.to_datetime(raw_df_date['创建时间'], errors='coerce')
        valid_pub = raw_df_date['publish_date'].dropna()
        if not valid_pub.empty:
            min_date_all = valid_pub.min().date()
            max_date_all = valid_pub.max().date()
            selected_date = st.date_input("📅 选择检查日期", value=max_date_all, min_value=min_date_all)
            mask_today = (raw_df_date['publish_date'].dt.date == selected_date)
            daily_stats = raw_df_date[mask_today].groupby('作者昵称').size().reset_index(name='当天发布数')
            all_authors = sorted(raw_df_date['作者昵称'].dropna().unique())
            author_status = pd.DataFrame({'作者昵称': all_authors}).merge(daily_stats, on='作者昵称', how='left')
            author_status['当天发布数'] = author_status['当天发布数'].fillna(0).astype(int)
            author_status['发布状态'] = author_status['当天发布数'].apply(lambda x: '✅ 已发布' if x > 0 else '❌ 未发布')
            filter_option = st.radio("筛选作者：", ["全部作者", "仅未发布作者", "仅已发布作者"], horizontal=True)
            if filter_option == "仅未发布作者":
                author_status = author_status[author_status['当天发布数'] == 0]
            elif filter_option == "仅已发布作者":
                author_status = author_status[author_status['当天发布数'] > 0]
            st.write(f"### {selected_date} 作者发布情况 (共 {len(author_status)} 位)")
            st.dataframe(author_status, use_container_width=True)
            st.info(f"📊 摘要：共 {len(all_authors)} 位作者，其中 {len(daily_stats)} 位当天发布了视频，合计发布 {daily_stats['当天发布数'].sum()} 个视频。")
        else:
            st.info("原始数据中无有效发布日期，无法进行单日监控。")
    else:
        st.info("原始数据缺少'创建时间'或'作者昵称'列，无法进行单日监控。")

    # 原始数据预览
    st.subheader("📄 原始数据预览（筛选后）")
    display_cols = ['作者昵称', '视频描述', '点赞数', '评论数', '分享数', '收藏数', '粉丝数', '创建时间']
    existing = [c for c in display_cols if c in raw_filtered.columns]
    preview_df = raw_filtered[existing] if existing else raw_filtered
    show_all = st.checkbox("显示全部数据（默认仅前100行）")
    st.dataframe(preview_df if show_all else preview_df.head(100), use_container_width=True)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📌 说明")
    st.sidebar.info("数据每日自动同步至 GitHub，看板每小时自动刷新缓存。")

if __name__ == "__main__":
    main()