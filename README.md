# 量化交易策略分析应用

基于 Streamlit 的模块化量化策略 WebApp，用于金融历史数据分析、策略回测、模型比较和离线 HTML 报告导出。

## 最终提交入口

- WebApp 入口：`app.py`
- 离线 HTML 报告：`reports/Final_Report.html`
- 依赖清单：`requirements.txt`
- 最终打包脚本：`scripts/prepare_final_zip.ps1`

## 本地运行

推荐环境：`Python 3.10+`

1. 创建虚拟环境。

```bash
python -m venv .venv
```

2. 激活虚拟环境。

```bash
.venv\Scripts\activate
```

3. 安装依赖。

```bash
pip install -r requirements.txt
```

4. 启动 WebApp。

```bash
streamlit run app.py
```

5. 打开浏览器访问：`http://localhost:8501/strategy`

可直接使用仓库内 `data/` 的样例数据；若分析其他股票且本地无缓存，应用会通过 `AkShare` 在线拉取数据，因此需要可用网络连接。

## Windows 快捷脚本

- 首次安装：`scripts\setup.bat`
- 启动应用：`scripts\start.bat`

## 功能概览

- 单股分析、策略信号生成与回测
- 多股票比较、风险收益分析与组合模拟
- Baseline / Proposed Model 对比
- Walk-forward 验证、模型评估与指标检查
- 单股 / 多股离线 HTML 导出

## 项目结构

```text
stratagy/
├── app.py                    # Streamlit 入口
├── core/                     # 数据、指标、信号、回测、评估、优化
├── ui/                       # 页面、侧边栏、主题、HTML 导出
├── data/                     # 本地样例与缓存数据
├── reports/                  # 最终离线 HTML 报告
├── scripts/                  # 本地启动与最终打包脚本
├── deploy/                   # 服务器部署脚本
├── document/                 # 项目文档
├── requirements.txt          # 运行依赖
└── AI_CONTEXT.md             # 项目级 AI 协作上下文
```

## 最终 ZIP 打包

生成课程要求的 `Final_gpXX.zip`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_final_zip.ps1 -GroupNumber 01
```

脚本会自动：

- 复制运行所需源码与相关文件
- 排除 `.git`、`__pycache__`、`.venv`、本地缓存和临时输出
- 生成 `dist/Final_gp01.zip`

建议在另一台没有运行过本项目的电脑上，解压后严格按本 README 再跑一遍冒烟测试。

## 云端部署

- 对外子路径：`/strategy`
- 服务器应用目录：`/opt/stratagy`
- 常用同步脚本：`deploy/sync.bat`
- 全量上传脚本：`deploy/upload_and_deploy.bat`

## 免责声明

本应用仅供课程学习与研究使用，不构成任何投资建议。
