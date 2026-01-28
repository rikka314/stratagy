# 诊断实验工作指南

## 🚀 快速开始

### 1. 领取任务
在 `DIAGNOSIS_TASKS.md` 中找到你的任务，在"负责人"处填写你的名字。

### 2. 创建工作分支
```bash
cd "/Users/rikka/Library/Mobile Documents/com~apple~CloudDocs/Learn/20_Projects/2026_SPRING/AIE1902/课堂内容/stratagy"

# 创建并切换到你的任务分支
git checkout -b task1-yourname  # 替换为你的任务编号和名字
```

### 3. 安装依赖
```bash
# 激活虚拟环境（如果还没有）
source .venv/bin/activate

# 安装额外的分析包
pip install jupyter seaborn scipy statsmodels
```

### 4. 开始工作

#### 选项 A：使用 Jupyter Notebook（推荐）
```bash
# 启动 Jupyter
jupyter notebook diagnosis/notebooks/

# 打开或创建对应的 task{n}_*.ipynb 文件
```

#### 选项 B：使用 Python 脚本
```bash
# 创建你的脚本
cd diagnosis/notebooks
touch task{n}_your_script.py

# 编辑并运行
python task{n}_your_script.py
```

### 5. 使用共享工具
在你的代码中导入共享函数：

```python
import sys
sys.path.append('../..')  # 如果在 notebooks 文件夹中
from utils import (
    load_data, 
    add_all_indicators,
    calculate_all_metrics,
    plot_equity_curves,
    # ... 其他函数
)

# 加载数据
df = load_data('aapl', data_dir='../../data')

# 添加技术指标
df = add_all_indicators(df)
```

---

## 📂 文件组织规范

### 保存结果
```python
from utils import save_results_to_csv

# 保存 CSV
save_results_to_csv(your_dataframe, 'task1_results.csv')

# 保存图片
plt.savefig('../figures/task1_your_chart.png', dpi=300, bbox_inches='tight')
```

### 命名规范
- Notebook: `task{n}_{description}.ipynb`
- 脚本: `task{n}_{description}.py`
- 数据结果: `task{n}_{description}.csv`
- 图表: `task{n}_{description}.png`

例如：
- `task1_data_quality.ipynb`
- `task2_factor_ic_analysis.csv`
- `task3_strategy_comparison.png`

---

## 🎯 各任务快速链接

| 任务 | 描述 | 优先级 | 预计时长 |
|------|------|--------|----------|
| [Task 1](DIAGNOSIS_TASKS.md#task-1-数据质量检查与基础分析-) | 数据质量检查 | 🔴 High | 3-4h |
| [Task 2](DIAGNOSIS_TASKS.md#task-2-技术指标有效性分析-) | 因子有效性分析 | 🔴 High | 4-5h |
| [Task 3](DIAGNOSIS_TASKS.md#task-3-简化策略对比实验-) | 策略对比实验 | 🟡 Medium | 4-5h |
| [Task 4](DIAGNOSIS_TASKS.md#task-4-参数敏感性分析-) | 参数敏感性分析 | 🟡 Medium | 5-6h |
| [Task 5](DIAGNOSIS_TASKS.md#task-5-交易行为分析-) | 交易行为分析 | 🟢 Low | 3-4h |
| [Task 6](DIAGNOSIS_TASKS.md#task-6-整合报告与可视化-dashboard-) | 整合报告 | 🔴 High | 4-5h |

---

## 📝 提交工作成果

### 1. 检查清单
- [ ] 代码可以运行（无错误）
- [ ] 所有图表清晰可读
- [ ] 添加了必要的注释
- [ ] 结果文件已保存到正确位置
- [ ] 更新了 notebook 中的"总结与发现"部分

### 2. 提交到 Git
```bash
# 添加你的更改
git add diagnosis/notebooks/task{n}_*
git add diagnosis/results/task{n}_*
git add diagnosis/figures/task{n}_*

# 提交
git commit -m "[Task{n}] 完成任务描述

完成内容:
- 完成了xxx分析
- 发现了xxx问题
- 生成了xxx图表

关键发现:
- 发现1
- 发现2

下一步建议:
- 建议1
"

# 推送到远程
git push origin task{n}-yourname
```

### 3. 创建 Pull Request
1. 在 GitHub 上创建 PR
2. 标题：`[Task{n}] 任务描述 - 你的名字`
3. 描述中包含关键发现和图表截图
4. 请求其他成员 Review

---

## 💡 提示和技巧

### 常用代码片段

#### 1. 加载和预处理数据
```python
from utils import load_data, add_all_indicators

df = load_data('aapl', data_dir='../../data')
df = add_all_indicators(df)
```

#### 2. 计算策略表现
```python
from utils import calculate_all_metrics

# 假设你有策略收益序列
strategy_returns = df['strategy_return'].dropna()
equity = (1 + strategy_returns).cumprod()

# 计算所有指标
metrics = calculate_all_metrics(strategy_returns, equity)
print(metrics)
```

#### 3. 绘制对比图
```python
from utils import plot_equity_curves

curves = {
    'Buy & Hold': buy_hold_equity,
    'Strategy 1': strategy1_equity,
    'Strategy 2': strategy2_equity,
}

plot_equity_curves(curves, 
                   title="策略权益曲线对比",
                   save_path='../figures/task3_comparison.png')
```

#### 4. 计算 IC 值
```python
from utils import calculate_ic

# 计算某个因子的 IC
df['forward_return_5d'] = df['close'].pct_change(5).shift(-5)
ic = calculate_ic(df['rsi'], df['forward_return_5d'])
print(f"RSI 的 5 日 IC: {ic:.4f}")
```

### 调试技巧

1. **数据量太大？** 先用小样本测试：
```python
df_sample = df.tail(1000)  # 只用最近 1000 天
```

2. **计算很慢？** 使用缓存：
```python
import pickle

# 保存中间结果
with open('temp_results.pkl', 'wb') as f:
    pickle.dump(results, f)

# 下次加载
with open('temp_results.pkl', 'rb') as f:
    results = pickle.load(f)
```

3. **遇到 NaN？** 先检查数据：
```python
print(df.isnull().sum())
df = df.dropna()  # 或 df.fillna(method='ffill')
```

---

## 🆘 遇到问题？

### 常见问题

**Q: 找不到 utils 模块？**
```python
# 确保路径正确
import sys
sys.path.append('../..')  # 回到项目根目录
from utils import *
```

**Q: 图表无法保存？**
```bash
# 确保目录存在
mkdir -p ../figures
```

**Q: 数据加载失败？**
```python
# 检查路径
import os
print(os.path.exists('../../data/aapl_daily.csv'))
```

**Q: Jupyter Notebook 无法启动？**
```bash
# 确保在虚拟环境中
source .venv/bin/activate
pip install jupyter
```

### 寻求帮助

1. **技术问题**：在项目群聊中询问
2. **任务理解**：查看 `DIAGNOSIS_TASKS.md` 详细说明
3. **代码参考**：查看 `task1_data_quality.ipynb` 示例
4. **工具函数**：查看 `utils.py` 中的文档字符串

---

## 📅 每日工作流程建议

### 上午（9:00 - 12:00）
1. 拉取最新代码：`git pull origin main`
2. 参加站会（10:00）
3. 专注完成任务主体部分

### 下午（14:00 - 18:00）
1. 完成可视化和分析
2. 整理结果和文档
3. 提交 PR 并请求 Review

### 晚上（可选）
1. Review 其他成员的 PR
2. 整合反馈，修改代码

---

## ✅ 成功标准

一个完成的任务应该包含：

1. **代码**
   - 可运行的 Notebook 或脚本
   - 清晰的注释和文档
   - 使用共享的 utils 函数

2. **结果**
   - CSV 文件（如适用）
   - 至少 2-3 张高质量图表
   - 结果文件命名规范

3. **分析**
   - "总结与发现"部分
   - 关键指标和结论
   - 对后续工作的建议

4. **文档**
   - Git commit 信息完整
   - PR 描述详细
   - 更新 DIAGNOSIS_TASKS.md 进度

---

## 🎉 完成后

1. 在团队会议上分享你的发现
2. 帮助 Review 其他成员的工作
3. 参与最终报告的编写（Task 6）
4. 庆祝完成！🎊

---

**项目仓库**: 本地路径  
**最后更新**: 2026-01-22  
**问题反馈**: 项目群聊

**祝工作顺利！有问题随时沟通 💪**
