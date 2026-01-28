"""
生成静态HTML报告的脚本
用于导出Streamlit应用的分析结果
"""

import os
import base64
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

def generate_html_report(
    stock_data_dict: dict,
    comparison_stats: pd.DataFrame,
    corr_fig: go.Figure,
    price_fig: go.Figure,
    output_file: str = "stock_analysis_report.html"
):
    """
    生成包含所有图表和分析的HTML报告
    
    Parameters:
    -----------
    stock_data_dict : dict
        股票数据字典
    comparison_stats : pd.DataFrame
        对比统计数据
    corr_fig : go.Figure
        相关性热图
    price_fig : go.Figure
        价格对比图
    output_file : str
        输出文件名
    """
    
    # 将图表转换为HTML
    price_html = pio.to_html(price_fig, include_plotlyjs='cdn', full_html=False)
    corr_html = pio.to_html(corr_fig, include_plotlyjs=False, full_html=False)
    
    # 生成统计表格HTML
    stats_html = comparison_stats.to_html(
        index=False,
        classes='stats-table',
        border=0
    )
    
    # 生成HTML内容
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股票策略分析报告 - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #2c3e50;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.95;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 50px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            display: flex;
            align-items: center;
        }}
        
        .section-title::before {{
            content: '📊';
            margin-right: 15px;
            font-size: 1.2em;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}
        
        .metric-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }}
        
        .metric-label {{
            font-size: 0.9em;
            color: #7f8c8d;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .metric-value {{
            font-size: 2em;
            color: #2c3e50;
            font-weight: 700;
        }}
        
        .metric-change {{
            font-size: 0.9em;
            margin-top: 5px;
        }}
        
        .positive {{
            color: #27ae60;
        }}
        
        .negative {{
            color: #e74c3c;
        }}
        
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        
        .stats-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 10px;
            overflow: hidden;
        }}
        
        .stats-table thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .stats-table th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        
        .stats-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #ecf0f1;
        }}
        
        .stats-table tbody tr:hover {{
            background: #f8f9fa;
        }}
        
        .stats-table tbody tr:last-child td {{
            border-bottom: none;
        }}
        
        .info-box {{
            background: #e8f4f8;
            border-left: 4px solid #3498db;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        
        .info-box p {{
            margin: 0;
            color: #2c3e50;
        }}
        
        .footer {{
            background: #34495e;
            color: white;
            text-align: center;
            padding: 30px;
            font-size: 0.9em;
        }}
        
        .footer p {{
            margin: 5px 0;
        }}
        
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
            }}
            
            .metric-card {{
                break-inside: avoid;
            }}
        }}
        
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 1.8em;
            }}
            
            .content {{
                padding: 20px;
            }}
            
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 报告头部 -->
        <div class="header">
            <h1>📊 股票策略分析报告</h1>
            <p>多股票对比与相关性分析</p>
            <p style="font-size: 0.9em; margin-top: 10px; opacity: 0.8;">
                生成时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
            </p>
        </div>
        
        <!-- 主要内容 -->
        <div class="content">
            <!-- 概览指标 -->
            <div class="section">
                <h2 class="section-title">核心指标</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">分析股票数量</div>
                        <div class="metric-value">{len(stock_data_dict)}</div>
                        <div class="metric-change">只</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">股票代码</div>
                        <div class="metric-value" style="font-size: 1.3em;">{', '.join(stock_data_dict.keys())}</div>
                    </div>
                </div>
            </div>
            
            <!-- 价格对比图 -->
            <div class="section">
                <h2 class="section-title">归一化价格走势对比</h2>
                <div class="info-box">
                    <p>💡 所有股票的起始价格都归一化为100，方便直观对比涨跌幅度</p>
                </div>
                <div class="chart-container">
                    {price_html}
                </div>
            </div>
            
            <!-- 相关性分析 -->
            <div class="section">
                <h2 class="section-title">股票相关性分析</h2>
                <div class="info-box">
                    <p>💡 相关系数接近1表示走势相似（正相关），接近-1表示走势相反（负相关），接近0表示无明显相关性</p>
                </div>
                <div class="chart-container">
                    {corr_html}
                </div>
            </div>
            
            <!-- 详细统计 -->
            <div class="section">
                <h2 class="section-title">详细统计数据</h2>
                {stats_html}
            </div>
            
            <!-- 分析说明 -->
            <div class="section">
                <h2 class="section-title">技术说明</h2>
                <div class="info-box">
                    <p><strong>📈 数据来源:</strong> AkShare API（美股日线数据）</p>
                </div>
                <div class="info-box">
                    <p><strong>🔬 分析方法:</strong></p>
                    <ul style="margin: 10px 0 0 20px;">
                        <li>归一化算法: 价格/起始价格 × 100</li>
                        <li>相关性计算: Pearson相关系数（基于日收益率）</li>
                        <li>数据对齐: 仅使用所有股票的共同交易日</li>
                    </ul>
                </div>
                <div class="info-box">
                    <p><strong>⚠️ 免责声明:</strong> 本报告仅供学习研究使用，不构成投资建议。投资有风险，入市需谨慎。</p>
                </div>
            </div>
        </div>
        
        <!-- 页脚 -->
        <div class="footer">
            <p><strong>策略实验室 v2.0</strong></p>
            <p>Powered by Streamlit + Plotly + AkShare</p>
            <p style="margin-top: 10px; opacity: 0.8;">© 2026 AIE1902 课程项目</p>
        </div>
    </div>
</body>
</html>
"""
    
    # 保存HTML文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return output_file


# 示例使用
if __name__ == "__main__":
    print("请在 Streamlit 应用中使用此功能")
    print("使用方法：在应用界面点击'导出HTML报告'按钮")
