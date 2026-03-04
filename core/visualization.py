"""
可视化模块
==========
多股票对比、相关性热图、相对强弱、风险收益散点、周期收益热图、因子评分对比。
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.indicators import add_indicators
from core.signals import compute_signals


# ──────────────────────────────────────────────────────────────
# 1) 多股票归一化价格对比
# ──────────────────────────────────────────────────────────────
def create_multi_stock_comparison_chart(stock_data_dict: dict, title: str = "多股票价格对比（归一化）") -> go.Figure:
    """
    创建多股票归一化价格对比的交互式图表
    
    Parameters:
    -----------
    stock_data_dict : dict
        {股票代码: DataFrame} 字典
    title : str
        图表标题
    
    Returns:
    --------
    go.Figure
        Plotly 图表对象
    """
    fig = go.Figure()
    
    # 颜色方案 - 使用专业的配色
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    for idx, (symbol, df) in enumerate(stock_data_dict.items()):
        if df is None or df.empty:
            continue
        
        # 归一化价格（起点=100）
        normalized_price = (df['close'] / df['close'].iloc[0]) * 100
        
        # 计算收益率用于hover显示
        total_return = ((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100
        
        # 添加轨迹
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=normalized_price,
            mode='lines',
            name=f'{symbol} ({total_return:+.1f}%)',
            line=dict(color=colors[idx % len(colors)], width=2.5),
            hovertemplate=(
                f'<b>{symbol}</b><br>' +
                '日期: %{x|%Y-%m-%d}<br>' +
                '归一化价格: %{y:.2f}<br>' +
                f'期间收益: {total_return:+.2f}%<br>' +
                '<extra></extra>'
            ),
            legendgroup=symbol,
            showlegend=True,
        ))
    
    # 添加基准线（起点）
    if stock_data_dict:
        first_date = list(stock_data_dict.values())[0]['date'].iloc[0]
        last_date = list(stock_data_dict.values())[0]['date'].iloc[-1]
        
        fig.add_hline(
            y=100,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            annotation_text="起点基准 (100)",
            annotation_position="right"
        )
    
    # 更新布局 - 专业金融风格
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=22, color='#2c3e50', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.98,
            yanchor='top'
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            rangeslider=dict(
                visible=True,
                thickness=0.05,
                bgcolor='#f8f9fa',
                bordercolor='#bdc3c7',
                borderwidth=1
            ),
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1周", step="day", stepmode="backward"),
                    dict(count=1, label="1月", step="month", stepmode="backward"),
                    dict(count=3, label="3月", step="month", stepmode="backward"),
                    dict(count=6, label="6月", step="month", stepmode="backward"),
                    dict(count=1, label="1年", step="year", stepmode="backward"),
                    dict(step="all", label="全部"),
                ]),
                bgcolor='#ecf0f1',
                activecolor='#3498db',
                font=dict(size=10),
                x=0,
                y=1.05,
                xanchor='left',
                yanchor='top'
            ),
        ),
        yaxis=dict(
            title='归一化价格（起点=100）',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            zeroline=True,
            zerolinecolor='#95a5a6',
            zerolinewidth=1.5,
            tickformat='.1f',
        ),
        hovermode='x unified',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=650,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(255,255,255,0.95)',
            bordercolor='#bdc3c7',
            borderwidth=1.5,
            font=dict(size=11),
            title=dict(text='股票（期间收益）', font=dict(size=12, color='#2c3e50'))
        ),
        margin=dict(l=70, r=40, t=100, b=60),
        font=dict(family='Arial, sans-serif'),
    )
    
    return fig


# ──────────────────────────────────────────────────────────────
# 2) 相关性热图
# ──────────────────────────────────────────────────────────────
def create_correlation_heatmap(stock_data_dict: dict) -> go.Figure:
    """创建股票收益率相关性热图 - 改进版，支持日期对齐"""
    
    # 准备日收益率数据，使用日期作为索引
    returns_series = {}
    for symbol, df in stock_data_dict.items():
        if df is not None and len(df) > 1:
            # 确保有 date 列并设置为索引
            temp_df = df.copy()
            if 'date' in temp_df.columns:
                temp_df['date'] = pd.to_datetime(temp_df['date'])
                temp_df = temp_df.set_index('date')
            
            # 计算日收益率
            returns = temp_df['close'].pct_change().dropna()
            returns_series[symbol] = returns
    
    if len(returns_series) < 2:
        return None
    
    # 使用日期索引对齐所有股票数据
    # 找到所有股票的共同交易日
    returns_df = pd.DataFrame(returns_series)
    
    # 删除任何含有 NaN 的行（确保所有股票在同一天都有数据）
    returns_df = returns_df.dropna()
    
    # 检查是否有足够的数据
    if len(returns_df) < 10:  # 至少需要10天的数据才能计算有意义的相关性
        return None
    
    # 计算相关性矩阵
    corr_matrix = returns_df.corr()
    
    # 创建注释文本（显示相关系数和数据点数）
    annotations_text = []
    for i in range(len(corr_matrix)):
        row_text = []
        for j in range(len(corr_matrix.columns)):
            corr_val = corr_matrix.iloc[i, j]
            if i == j:
                row_text.append(f'{corr_val:.2f}')
            else:
                row_text.append(f'{corr_val:.3f}')
        annotations_text.append(row_text)
    
    # 创建热图
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        colorscale=[
            [0.0, '#d73027'],      # 深红色 (-1)
            [0.25, '#fc8d59'],     # 橙红色 (-0.5)
            [0.5, '#f7f7f7'],      # 白色 (0)
            [0.75, '#91bfdb'],     # 浅蓝色 (0.5)
            [1.0, '#4575b4']       # 深蓝色 (1)
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        text=annotations_text,
        texttemplate='%{text}',
        textfont={"size": 14, "color": "white", "family": "Arial Black"},
        colorbar=dict(
            title=dict(
                text="相关系数",
                font=dict(size=13, color='#2c3e50'),
                side="right"
            ),
            tickmode="linear",
            tick0=-1,
            dtick=0.25,
            tickfont=dict(size=11),
            len=0.8,
            thickness=15,
        ),
        hovertemplate=(
            '<b>%{y} vs %{x}</b><br>' +
            '相关系数: %{z:.4f}<br>' +
            f'共同交易日: {len(returns_df)}<br>' +
            '<extra></extra>'
        ),
    ))
    
    fig.update_layout(
        title=dict(
            text=f'股票收益率相关性矩阵（基于 {len(returns_df)} 个共同交易日）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.95,
            yanchor='top'
        ),
        xaxis=dict(
            title='',
            side='bottom',
            tickfont=dict(size=12, color='#2c3e50'),
            showgrid=False,
        ),
        yaxis=dict(
            title='',
            tickfont=dict(size=12, color='#2c3e50'),
            showgrid=False,
        ),
        height=550,
        width=None,  # 自适应宽度
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        margin=dict(l=100, r=100, t=100, b=80),
    )
    
    # 添加说明文本
    fig.add_annotation(
        text='💡 提示：接近1表示正相关，接近-1表示负相关，接近0表示无相关性',
        xref='paper', yref='paper',
        x=0.5, y=-0.12,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=11, color='#7f8c8d', family='Arial'),
    )
    
    return fig


# ──────────────────────────────────────────────────────────────
# 3) 相对强弱对比
# ──────────────────────────────────────────────────────────────
def create_relative_strength_chart(stock_data_dict: dict, benchmark: str = "equal_weight") -> go.Figure:
    """
    创建相对强弱对比图（Relative Strength Comparison）

    【原理说明】
    相对强弱指标（RS）= 个股归一化价格 / 基准归一化价格。
    - RS 曲线上升 → 该股票跑赢基准（即使股价本身在跌，只要跌得比基准少也算跑赢）
    - RS 曲线下降 → 该股票跑输基准
    - RS = 1.0 水平线表示与基准持平

    【对决策的影响】
    动量交易者倾向于买入相对强势的股票、回避相对弱势的股票。
    通过 RS 曲线可以清晰地看到资金应该往哪个方向分配。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        benchmark: 基准模式，"equal_weight"=所有股票等权平均，或指定某只股票代码

    返回：
        Plotly 图表对象，失败返回 None
    """
    if len(stock_data_dict) < 2:
        return None

    # 步骤1：构建各股票的归一化收盘价序列（起点=1.0），按日期对齐
    norm_series = {}
    for sym, df in stock_data_dict.items():
        if df is None or len(df) < 2 or 'close' not in df.columns:
            continue
        s = df.set_index('date')['close'].sort_index()
        s = s / s.iloc[0]  # 归一化到起点=1.0
        norm_series[sym] = s

    if len(norm_series) < 2:
        return None

    # 合并成 DataFrame，日期对齐（取交集）
    norm_df = pd.DataFrame(norm_series)
    norm_df = norm_df.dropna()

    if len(norm_df) < 2:
        return None

    # 步骤2：计算基准
    if benchmark == "equal_weight" or benchmark not in norm_df.columns:
        benchmark_series = norm_df.mean(axis=1)  # 等权平均
        benchmark_label = "等权平均基准"
    else:
        benchmark_series = norm_df[benchmark]
        benchmark_label = f"{benchmark} 基准"

    # 步骤3：计算相对强弱 RS = 个股 / 基准
    rs_df = norm_df.div(benchmark_series, axis=0)

    # 步骤4：绘图
    # 使用与项目一致的配色
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#636efa', '#ef553b', '#00cc96', '#ab63fa', '#ffa15a',
    ]

    fig = go.Figure()

    for i, sym in enumerate(rs_df.columns):
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=rs_df.index,
            y=rs_df[sym],
            name=sym,
            mode='lines',
            line=dict(color=color, width=2),
            hovertemplate=(
                f'<b>{sym}</b><br>'
                '日期: %{x|%Y-%m-%d}<br>'
                '相对强弱: %{y:.4f}<br>'
                '<extra></extra>'
            ),
        ))

    # 添加基准线 RS=1.0
    fig.add_hline(
        y=1.0,
        line_dash='dash',
        line_color='rgba(128,128,128,0.6)',
        line_width=1.5,
        annotation_text='基准线 (RS=1.0)',
        annotation_position='top right',
        annotation_font=dict(size=11, color='#7f8c8d'),
    )

    fig.update_layout(
        title=dict(
            text=f'相对强弱对比（基准: {benchmark_label}）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#f0f0f0',
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            title='相对强弱 (RS)',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            hoverformat='.4f',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=500,
        margin=dict(l=60, r=60, t=80, b=80),
        legend=dict(
            orientation='h',
            yanchor='bottom', y=-0.25,
            xanchor='center', x=0.5,
            font=dict(size=12),
        ),
        hovermode='x unified',
    )

    # 底部注释
    fig.add_annotation(
        text=f'RS > 1.0 表示跑赢{benchmark_label}，RS < 1.0 表示跑输{benchmark_label}',
        xref='paper', yref='paper',
        x=0.5, y=-0.32,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=11, color='#7f8c8d', family='Arial'),
    )

    return fig


# ──────────────────────────────────────────────────────────────
# 4) 风险收益散点图
# ──────────────────────────────────────────────────────────────
def create_risk_return_scatter(stock_data_dict: dict) -> go.Figure:
    """
    创建风险收益散点图（Risk-Return Scatter Plot）
    
    【原理说明】
    风险收益散点图是现代投资组合理论（MPT）中最基础的可视化工具：
    - 横轴：年化波动率（衡量风险，波动越大风险越高）
    - 纵轴：年化收益率（衡量回报）
    - 理想标的位于左上角（高收益 + 低风险）
    - 劣质标的位于右下角（低收益 + 高风险）
    
    【计算方法】
    - 年化收益率 = (1 + 总收益率) ^ (252 / 交易天数) - 1
    - 年化波动率 = 日收益率标准差 × √252
    - 夏普比率 = 年化收益率 / 年化波动率（简化版，无风险利率设为0）
    
    【对决策的影响】
    帮助投资者在多只股票中快速识别风险收益特征最优的标的，
    支持资产配置决策。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
    
    返回：
        Plotly 散点图对象，失败返回 None
    """
    
    symbols = []
    ann_returns = []    # 年化收益率（百分比）
    ann_vols = []       # 年化波动率（百分比）
    sharpe_ratios = []  # 夏普比率
    
    for symbol, df in stock_data_dict.items():
        if df is None or len(df) < 2:
            continue
        
        try:
            # 计算日收益率
            daily_returns = df['close'].pct_change().dropna()
            if daily_returns.empty:
                continue
            
            # 计算年化收益率（假设一年 252 个交易日）
            total_return = df['close'].iloc[-1] / df['close'].iloc[0] - 1
            trading_days = len(df)
            
            # 安全检查：total_return 不能 <= -1（否则底数为负，幂运算出错）
            if total_return <= -1:
                annualized_return = -0.99  # 钳位到 -99%，避免数学错误
            else:
                annualized_return = (1 + total_return) ** (252 / trading_days) - 1
            
            # 计算年化波动率
            annualized_volatility = daily_returns.std() * np.sqrt(252)
            
            # 计算夏普比率（简化版，无风险利率 = 0）
            if annualized_volatility > 0:
                sr = annualized_return / annualized_volatility
            else:
                sr = 0.0
            
            symbols.append(symbol)
            ann_returns.append(annualized_return * 100)
            ann_vols.append(annualized_volatility * 100)
            sharpe_ratios.append(round(sr, 2))
            
        except Exception:
            # 跳过计算失败的股票，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    fig = go.Figure()
    
    # 添加散点（hover 包含夏普比率）
    fig.add_trace(go.Scatter(
        x=ann_vols,
        y=ann_returns,
        mode='markers+text',
        text=symbols,
        textposition='top center',
        marker=dict(
            size=15,
            color=sharpe_ratios,      # 颜色映射到夏普比率
            colorscale='RdYlGn',      # 红（差）→ 黄 → 绿（好）
            showscale=True,
            colorbar=dict(title='夏普比率'),
            line=dict(width=1.5, color='DarkSlateGrey'),
        ),
        customdata=np.column_stack([sharpe_ratios]),
        hovertemplate=(
            '<b>%{text}</b><br>'
            '年化波动率 (风险): %{x:.2f}%<br>'
            '年化收益率 (回报): %{y:.2f}%<br>'
            '夏普比率: %{customdata[0]:.2f}<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加象限辅助线（以中位数为界）
    if len(ann_vols) > 1:
        median_vol = np.median(ann_vols)
        median_ret = np.median(ann_returns)
        
        fig.add_vline(x=median_vol, line_dash='dash', line_color='gray', opacity=0.5)
        fig.add_hline(y=median_ret, line_dash='dash', line_color='gray', opacity=0.5)
        
        # 象限标注
        min_vol, max_vol = min(ann_vols), max(ann_vols)
        min_ret, max_ret = min(ann_returns), max(ann_returns)
        
        fig.add_annotation(
            x=min_vol, y=max_ret, text='⭐ 高收益低风险',
            showarrow=False, font=dict(color='green', size=11),
            xanchor='left', yanchor='top', bgcolor='rgba(255,255,255,0.8)',
        )
        fig.add_annotation(
            x=max_vol, y=min_ret, text='⚠️ 低收益高风险',
            showarrow=False, font=dict(color='red', size=11),
            xanchor='right', yanchor='bottom', bgcolor='rgba(255,255,255,0.8)',
        )
    
    fig.update_layout(
        title=dict(
            text='风险-收益散点图（年化）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='年化波动率（风险）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1', zeroline=False,
        ),
        yaxis=dict(
            title='年化收益率（回报）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            zeroline=True, zerolinecolor='#95a5a6',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=550,
        margin=dict(l=80, r=80, t=80, b=80),
    )
    
    return fig


# ──────────────────────────────────────────────────────────────
# 5) 周期收益率热图
# ──────────────────────────────────────────────────────────────
def create_periodic_returns_heatmap(stock_data_dict: dict, period: str = "M") -> go.Figure:
    """
    创建周期收益率热图（Periodic Returns Heatmap）

    【原理说明】
    按月/季度/年展示每只股票的收益率：
    - 行 = 股票代码，列 = 时间周期
    - 颜色红绿色阶：绿=盈利，红=亏损

    【对决策的影响】
    帮助发现股票的季节性规律或在特定市场环境下的表现差异。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        period: 时间周期，"M"=月度，"Q"=季度，"Y"=年度

    返回：
        Plotly 热图对象，失败返回 None
    """
    if len(stock_data_dict) < 1:
        return None

    period_labels = {"M": "月度", "Q": "季度", "YE": "年度"}
    period_fmt = {"M": "%Y-%m", "Q": "%Y-Q", "YE": "%Y"}

    # 对每只股票计算周期收益率
    all_returns = {}
    for sym, df in stock_data_dict.items():
        if df is None or len(df) < 2 or 'close' not in df.columns or 'date' not in df.columns:
            continue
        s = df.set_index('date')['close'].sort_index()
        # resample 到指定周期，取最后一个收盘价，再算周期收益率
        resampled = s.resample(period).last().dropna()
        pct = resampled.pct_change().dropna() * 100  # 转为百分比
        if len(pct) < 1:
            continue
        # 生成时间标签
        if period == "Q":
            labels = [f"{d.year}-Q{(d.month - 1) // 3 + 1}" for d in pct.index]
        else:
            fmt = period_fmt.get(period, "%Y-%m")
            labels = [d.strftime(fmt) for d in pct.index]
        all_returns[sym] = pd.Series(pct.values, index=labels)

    if not all_returns:
        return None

    # 合并成矩阵（股票 × 周期）
    returns_df = pd.DataFrame(all_returns).T  # 行=股票，列=周期

    # 限制最多显示列数，避免图表过宽
    max_cols = 24
    if returns_df.shape[1] > max_cols:
        returns_df = returns_df.iloc[:, -max_cols:]

    # 生成每个格子的文本标注
    text_matrix = returns_df.applymap(lambda x: f"{x:.1f}%" if pd.notna(x) else "")

    fig = go.Figure(data=go.Heatmap(
        z=returns_df.values,
        x=returns_df.columns.tolist(),
        y=returns_df.index.tolist(),
        text=text_matrix.values,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale=[
            [0.0, '#d32f2f'],    # 深红（大亏）
            [0.3, '#ef5350'],    # 红
            [0.45, '#ffcdd2'],   # 浅红
            [0.5, '#ffffff'],    # 白（零点）
            [0.55, '#c8e6c9'],   # 浅绿
            [0.7, '#66bb6a'],    # 绿
            [1.0, '#2e7d32'],    # 深绿（大涨）
        ],
        zmid=0,  # 白色对应零收益
        colorbar=dict(
            title=dict(text='收益率(%)', side='right'),
            ticksuffix='%',
            len=0.8,
        ),
        hovertemplate=(
            '<b>%{y}</b><br>'
            '周期: %{x}<br>'
            '收益率: %{z:.2f}%<br>'
            '<extra></extra>'
        ),
    ))

    period_name = period_labels.get(period, "月度")

    fig.update_layout(
        title=dict(
            text=f'股票{period_name}收益率热图',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='时间周期',
            title_font=dict(size=14, color='#34495e'),
            tickangle=-45,
            tickfont=dict(size=10),
            side='bottom',
        ),
        yaxis=dict(
            title='股票',
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
            autorange='reversed',  # 第一只股票在顶部
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=max(300, 80 * len(returns_df) + 150),  # 动态高度
        margin=dict(l=80, r=80, t=80, b=120),
    )

    return fig


# ──────────────────────────────────────────────────────────────
# 6) 因子评分横向对比
# ──────────────────────────────────────────────────────────────
def create_factor_score_comparison(stock_data_dict: dict, **kwargs) -> go.Figure:
    """
    创建多股票最新因子评分横向对比图
    
    【原理说明】
    使用项目中已有的 10 因子评分体系（动量/MACD/RSI/波动率/布林带/OBV/
    成交量/价格位置/回撤），对每只股票独立计算最新一天的综合因子评分，
    然后以柱状图横向对比，帮助用户在多标的中快速筛选。
    
    【计算流程】
    1. 对每只股票分别调用 add_indicators → compute_signals
    2. 提取最新一行的 factor_score 和 target_position
    3. 按评分降序排列绘制柱状图
    
    【颜色含义】
    - 绿色：策略建议重仓（≥80%）
    - 橙色：策略建议半仓（≥40%）
    - 蓝色：策略建议轻仓（>0%）
    - 灰色：策略建议空仓（0%）
    
    【对决策的影响】
    直接回答"当前哪只股票最值得买"的问题。
    红色虚线标示入场阈值，超过该线的股票是策略推荐买入的标的。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        **kwargs: 侧边栏传入的所有策略参数
    
    返回：
        Plotly 柱状图对象，失败返回 None
    """
    
    symbols = []
    scores = []
    target_positions = []
    percentiles = []
    
    for symbol, df in stock_data_dict.items():
        if df is None or len(df) <= 50:
            # 数据不足 50 行时无法可靠计算滚动指标，跳过
            continue
        
        try:
            # 计算技术指标
            df_indicators = add_indicators(
                df,
                rsi_period=kwargs.get('rsi_period', 14),
                macd_fast=kwargs.get('macd_fast', 12),
                macd_slow=kwargs.get('macd_slow', 26),
                macd_signal=kwargs.get('macd_signal', 9),
                ema_fast=kwargs.get('ema_fast', 20),
                ema_slow=kwargs.get('ema_slow', 60),
                adx_period=kwargs.get('adx_period', 14),
                atr_period=kwargs.get('atr_period', 14),
                bb_period=kwargs.get('bb_period', 20),
                bb_std=kwargs.get('bb_std', 2.0),
                indicator_period=kwargs.get('indicator_period', 20),
            )
            
            # 计算策略信号
            df_signals = compute_signals(
                df_indicators,
                rsi_lower=kwargs.get('rsi_lower', 30),
                rsi_upper=kwargs.get('rsi_upper', 70),
                adx_threshold=kwargs.get('adx_threshold', 20),
                momentum_short=kwargs.get('momentum_short', 5),
                momentum_long=kwargs.get('momentum_long', 20),
                score_lookback=kwargs.get('score_lookback', 30),
                score_mid_pct=kwargs.get('score_mid_pct', 0.6),
                score_high_pct=kwargs.get('score_high_pct', 0.8),
                weight_mom_short=kwargs.get('weight_mom_short', 1.0),
                weight_mom_long=kwargs.get('weight_mom_long', 1.0),
                weight_macd=kwargs.get('weight_macd', 1.0),
                weight_rsi=kwargs.get('weight_rsi', 0.5),
                weight_vol=kwargs.get('weight_vol', 0.5),
                entry_threshold=kwargs.get('entry_threshold', 0.5),
                exit_threshold=kwargs.get('exit_threshold', -0.5),
                use_trend_filter=kwargs.get('use_trend_filter', True),
                use_strength_filter=kwargs.get('use_strength_filter', True),
                use_rsi_filter=kwargs.get('use_rsi_filter', True),
                use_macd_filter=kwargs.get('use_macd_filter', True),
                use_voting_entry=kwargs.get('use_voting_entry', True),
                entry_vote_threshold=kwargs.get('entry_vote_threshold', 2.5),
                exit_min_signals=kwargs.get('exit_min_signals', 2),
                entry_min_signals=kwargs.get('entry_min_signals', 3),
            )
            
            # 获取最新一天的评分和目标仓位（统一使用 .get 安全访问）
            latest = df_signals.iloc[-1]
            score_val = float(latest.get('factor_score', 0.0))
            pos_val = float(latest.get('target_position', 0.0))
            pct_val = float(latest.get('factor_percentile', 0.0))
            
            symbols.append(symbol)
            scores.append(score_val)
            target_positions.append(pos_val)
            percentiles.append(pct_val)
            
        except Exception:
            # 某只股票计算失败时跳过，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    # 按评分降序排序
    sorted_indices = np.argsort(scores)[::-1]
    symbols = [symbols[i] for i in sorted_indices]
    scores = [scores[i] for i in sorted_indices]
    target_positions = [target_positions[i] for i in sorted_indices]
    percentiles = [percentiles[i] for i in sorted_indices]
    
    # 确定柱子颜色：根据目标仓位分档
    colors = []
    for pos in target_positions:
        if pos >= 0.8:
            colors.append('#2ca02c')   # 绿色（重仓）
        elif pos >= 0.4:
            colors.append('#ff7f0e')   # 橙色（半仓）
        elif pos > 0:
            colors.append('#1f77b4')   # 蓝色（轻仓）
        else:
            colors.append('#7f7f7f')   # 灰色（空仓）
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=symbols,
        y=scores,
        marker_color=colors,
        text=[f'{s:.2f}' for s in scores],
        textposition='auto',
        customdata=np.column_stack([target_positions, [p * 100 for p in percentiles]]),
        hovertemplate=(
            '<b>%{x}</b><br>'
            '因子评分: %{y:.2f}<br>'
            '建议仓位: %{customdata[0]:.0%}<br>'
            '评分分位数: %{customdata[1]:.1f}%<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加入场阈值辅助线
    entry_thr = kwargs.get('entry_threshold', 0.5)
    fig.add_hline(
        y=entry_thr,
        line_dash='dash',
        line_color='red',
        annotation_text=f'入场阈值 ({entry_thr})',
        annotation_position='top right',
    )
    
    fig.update_layout(
        title=dict(
            text='最新因子评分横向对比',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='股票代码',
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
        ),
        yaxis=dict(
            title='综合因子评分',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=450,
        margin=dict(l=60, r=60, t=80, b=80),
        showlegend=False,
    )
    
    # 底部图例说明
    fig.add_annotation(
        text='颜色说明: 🟩 重仓 (≥80%) | 🟧 半仓 (≥40%) | 🟦 轻仓 (>0%) | ⬜ 空仓 (0%)',
        xref='paper', yref='paper',
        x=0.5, y=-0.18,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=12, color='#7f8c8d'),
    )
    
    return fig
