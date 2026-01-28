# 📚 诊断实验文档索引

## 🚀 快速导航

### 给团队负责人
1. 📊 **[DIAGNOSIS_SETUP_COMPLETE.md](DIAGNOSIS_SETUP_COMPLETE.md)** - 开始这里！准备工作总结
2. 📋 **[DIAGNOSIS_TASKS.md](DIAGNOSIS_TASKS.md)** - 任务分解详细说明（15+ 页）
3. 🎯 **[diagnosis/PROJECT_OVERVIEW.md](diagnosis/PROJECT_OVERVIEW.md)** - 项目总览和计划

### 给任务执行者
1. 📖 **[diagnosis/README.md](diagnosis/README.md)** - 工作指南和快速开始
2. 📓 **[diagnosis/notebooks/task1_data_quality.ipynb](diagnosis/notebooks/task1_data_quality.ipynb)** - 示例模板
3. 🔧 **[utils.py](utils.py)** - 共享工具函数库

### 背景资料
1. 🔍 **[STRATEGY_ANALYSIS.md](STRATEGY_ANALYSIS.md)** - 问题诊断和改进方案
2. 📝 **[PROJECT_LOG.md](PROJECT_LOG.md)** - 原项目文档
3. 💻 **[app.py](app.py)** - 原始应用代码

---

## 📂 文件结构

```
stratagy/
│
├── 📖 核心文档
│   ├── DIAGNOSIS_SETUP_COMPLETE.md    ⭐ 开始这里
│   ├── DIAGNOSIS_TASKS.md             ⭐ 任务说明（主文档）
│   ├── STRATEGY_ANALYSIS.md           问题分析
│   ├── PROJECT_LOG.md                 原项目文档
│   └── INDEX.md                       本文件
│
├── 🛠️ 代码
│   ├── utils.py                       ⭐ 共享工具库
│   ├── app.py                         原始应用
│   └── requirements.txt               依赖列表
│
├── 📊 数据
│   └── data/
│       ├── aapl_daily.csv
│       └── tsla_daily.csv
│
└── 🔬 诊断实验工作区
    └── diagnosis/
        ├── PROJECT_OVERVIEW.md        项目总览
        ├── README.md                  ⭐ 工作指南
        │
        ├── notebooks/                 Jupyter Notebooks
        │   └── task1_data_quality.ipynb  ⭐ 示例模板
        │
        ├── results/                   CSV/JSON 结果
        ├── figures/                   图表
        └── reports/                   报告文档
```

---

## 🎯 按角色查看

### 我是项目经理
**阅读顺序**：
1. DIAGNOSIS_SETUP_COMPLETE.md（5 分钟）
2. diagnosis/PROJECT_OVERVIEW.md（10 分钟）
3. DIAGNOSIS_TASKS.md（30 分钟）

**关注点**：任务分配、时间安排、成功标准

### 我是数据分析师（Task 1, 2, 5）
**阅读顺序**：
1. diagnosis/README.md（10 分钟）
2. DIAGNOSIS_TASKS.md 中你的任务部分（20 分钟）
3. task1_data_quality.ipynb 示例（10 分钟）
4. utils.py 中的数据和统计函数（10 分钟）

**关键工具**：
- `load_data()`, `add_all_indicators()`
- `calculate_all_metrics()`, `calculate_ic()`
- `plot_equity_curves()`, `plot_correlation_matrix()`

### 我是策略开发者（Task 3, 4）
**阅读顺序**：
1. STRATEGY_ANALYSIS.md（15 分钟）- 理解问题
2. diagnosis/README.md（10 分钟）
3. DIAGNOSIS_TASKS.md 中 Task 3 或 4（20 分钟）
4. app.py 中的策略逻辑（20 分钟）

**关键工具**：
- `compute_signals()` - 原策略逻辑
- `simulate_strategy()` - 回测框架
- `calculate_sharpe_ratio()`, `calculate_max_drawdown()`

### 我是技术整合者（Task 6）
**阅读顺序**：
1. DIAGNOSIS_SETUP_COMPLETE.md（5 分钟）
2. 所有任务的交付物（1 小时）
3. DIAGNOSIS_TASKS.md 中 Task 6 部分（20 分钟）

**关注点**：整合报告、Dashboard、演示材料

---

## 📋 6 个任务快速参考

| 任务 | 文档位置 | 代码模板 | 时长 | 优先级 |
|------|----------|----------|------|--------|
| Task 1 | DIAGNOSIS_TASKS.md#task-1 | task1_data_quality.ipynb | 3-4h | 🔴 |
| Task 2 | DIAGNOSIS_TASKS.md#task-2 | 参考 Task 1 | 4-5h | 🔴 |
| Task 3 | DIAGNOSIS_TASKS.md#task-3 | 参考 app.py | 4-5h | 🟡 |
| Task 4 | DIAGNOSIS_TASKS.md#task-4 | 参考 Task 3 | 5-6h | 🟡 |
| Task 5 | DIAGNOSIS_TASKS.md#task-5 | 参考 Task 3 | 3-4h | 🟢 |
| Task 6 | DIAGNOSIS_TASKS.md#task-6 | 所有任务结果 | 4-5h | 🔴 |

---

## 🔧 常用命令速查

### 环境准备
```bash
cd "/Users/rikka/Library/Mobile Documents/com~apple~CloudDocs/Learn/20_Projects/2026_SPRING/AIE1902/课堂内容/stratagy"
source .venv/bin/activate
pip install jupyter seaborn scipy statsmodels
```

### 启动工作
```bash
# Jupyter Notebook
jupyter notebook diagnosis/notebooks/

# 查看文档
cat DIAGNOSIS_TASKS.md | grep "Task 1" -A 50
```

### 测试环境
```bash
python utils.py  # 运行工具库测试
python -c "from utils import *; print('✅')"
```

---

## 📞 获取帮助

### 文档查找
- **不知道从哪开始？** → `DIAGNOSIS_SETUP_COMPLETE.md`
- **任务不清楚？** → `DIAGNOSIS_TASKS.md`
- **代码怎么写？** → `task1_data_quality.ipynb` + `utils.py`
- **工具怎么用？** → `diagnosis/README.md`

### 问题排查
- **环境问题** → `diagnosis/README.md` 的"常见问题"部分
- **代码错误** → 查看 `utils.py` 的函数文档字符串
- **理解问题** → 重读 `STRATEGY_ANALYSIS.md`

### 团队沟通
- 技术问题：项目群聊
- 任务协调：每日站会（10:00, 17:00）
- 紧急事项：联系项目负责人

---

## ✅ 今天就开始！

1. 阅读 `DIAGNOSIS_SETUP_COMPLETE.md`（5 分钟）
2. 选择你的任务
3. 阅读对应的任务说明（20 分钟）
4. 开始编码！

**记住**：有问题随时查文档，随时问团队！

---

**最后更新**：2026-01-22 16:35  
**维护者**：项目团队  
**版本**：v1.0
