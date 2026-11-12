# Phase 0 快速启动指南

> **时间**: 1-2天
> **目标**: 确认是否需要重构，避免过度优化

---

## 立即执行的命令

### Step 1: 创建工作目录

```bash
cd D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy

# 创建Phase 0输出目录
mkdir -p model-test/outputs/phase0_diagnostic
mkdir -p document/phase0_reports
```

### Step 2: 审计现有专家表现

```bash
# 提取adaptive_router_v1的基准表现
python -c "
import pandas as pd

# 读取已有的model summary
df = pd.read_csv('model-test/outputs/full_us_deans_60/model_summary.csv')

# 筛选核心专家
core_experts = [
    'naive', 'drift', 'sm_bayesian', 'sm_genetic', 
    'fsm_bayesian', 'fsm_genetic', 'adaptive_router', 'cash'
]

baseline = df[df['model_id'].isin(core_experts)]

# 输出关键指标
print('=== Adaptive Router Baseline (US, 60 stocks) ===')
print(baseline[['model_id', 'median_sharpe', 'median_annret', 'median_maxdd', 'success_rate']].to_string(index=False))

# 保存
baseline.to_csv('model-test/outputs/phase0_diagnostic/expert_baseline.csv', index=False)
print('\n✓ Saved to: model-test/outputs/phase0_diagnostic/expert_baseline.csv')
"
```

**预期输出**:
```
model_id          median_sharpe  median_annret  median_maxdd  success_rate
naive             0.436          0.094          -0.331        1.0
sm_bayesian       0.034          0.001          -0.131        1.0
fsm_genetic       0.309          0.030          -0.147        1.0
adaptive_router   ???            ???            ???           ???
```

### Step 3: 专家相关性分析

创建分析脚本：

```bash
cat > model-test/phase0_expert_correlation.py << 'EOF'
"""Phase 0: 专家同质性审计"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def analyze_expert_correlation():
    """分析8个核心专家的daily return相关性"""
    
    # 1. 加载专家的daily returns (假设存在)
    # 如果没有，需要从回测结果重新计算
    output_dir = Path("model-test/outputs/full_us_deans_60")
    
    print("Searching for expert return data...")
    
    # 尝试找到专家的daily return
    # 通常在每个专家的detailed output中
    expert_returns = {}
    
    experts = [
        'naive', 'drift', 'sm_bayesian', 'sm_genetic',
        'fsm_bayesian', 'fsm_genetic', 'ml_lgbm', 'cash'
    ]
    
    for expert in experts:
        # 尝试读取该专家的return series
        # 路径可能是: outputs/full_us_deans_60/{expert}/daily_returns.csv
        try:
            ret_path = output_dir / expert / "daily_returns.csv"
            if ret_path.exists():
                expert_returns[expert] = pd.read_csv(ret_path, index_col=0)['return']
            else:
                print(f"Warning: {ret_path} not found")
        except Exception as e:
            print(f"Error loading {expert}: {e}")
    
    if len(expert_returns) < 2:
        print("\n❌ Error: Need at least 2 experts with daily return data")
        print("   Recommendation: Re-run backtest with --save-daily-returns flag")
        return None
    
    # 2. 对齐日期
    df = pd.DataFrame(expert_returns)
    df = df.dropna()
    
    print(f"\n✓ Loaded {len(df)} days × {len(expert_returns)} experts")
    
    # 3. 计算相关矩阵
    corr_matrix = df.corr(method='spearman')
    
    # 4. 可视化
    plt.figure(figsize=(10, 8))
    sns.heatmap(
        corr_matrix,
        annot=True,
        fmt='.2f',
        cmap='RdBu_r',
        vmin=-1, vmax=1,
        center=0,
        square=True,
        cbar_kws={"shrink": 0.8}
    )
    plt.title('Expert Daily Return Correlation (Spearman)', fontsize=14)
    plt.tight_layout()
    
    output_path = "model-test/outputs/phase0_diagnostic/expert_correlation.png"
    plt.savefig(output_path, dpi=150)
    print(f"\n✓ Saved heatmap: {output_path}")
    
    # 5. 统计分析
    upper_triangle = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    )
    
    avg_corr = upper_triangle.stack().mean()
    max_corr = upper_triangle.stack().max()
    high_corr_pairs = upper_triangle.stack()[upper_triangle.stack() > 0.8]
    
    print("\n=== Correlation Analysis ===")
    print(f"Average pairwise correlation: {avg_corr:.3f}")
    print(f"Maximum correlation: {max_corr:.3f}")
    print(f"High correlation pairs (>0.8): {len(high_corr_pairs)}")
    
    if len(high_corr_pairs) > 0:
        print("\nHigh correlation pairs:")
        for (e1, e2), corr in high_corr_pairs.items():
            print(f"  {e1} <-> {e2}: {corr:.3f}")
    
    # 6. 决策
    print("\n=== Phase 0 Decision ===")
    if avg_corr > 0.6:
        print("❌ FAIL: Average correlation > 0.6 (high homogeneity)")
        print("   → Proceed to Phase 1-2 (full reconstruction)")
    elif len(high_corr_pairs) > 3:
        print("⚠️  WARN: Multiple high-correlation pairs")
        print("   → Proceed to Phase 1 (incremental improvement)")
    else:
        print("✓ PASS: Experts are reasonably diverse")
        print("   → Consider stopping, or proceed to Phase 1 for marginal gains")
    
    # 7. 保存结果
    corr_matrix.to_csv("model-test/outputs/phase0_diagnostic/expert_correlation.csv")
    
    return corr_matrix

if __name__ == "__main__":
    analyze_expert_correlation()
EOF

python model-test/phase0_expert_correlation.py
```

### Step 4: 决策检查清单

根据上述结果，填写决策清单：

```markdown
## Phase 0 Decision Checklist

### P0.1: Adaptive Router Performance
- [ ] Sharpe > 0.5: ___
- [ ] Win rate > 55%: ___
- [ ] Max DD < 15%: ___
- [ ] Turnover < 100%: ___

**Score**: ___ / 4

### P0.2: Expert Homogeneity
- [ ] Average pairwise correlation: ___
- [ ] High corr pairs (>0.8): ___
- [ ] Max correlation: ___

### Decision:
- [ ] STOP (adaptive router already good, 4/4 passed)
- [ ] Phase 1 only (2-3/4 passed, low homogeneity)
- [ ] Phase 1-2 (≤1/4 passed, or high homogeneity)
- [ ] Phase 1-3 (full reconstruction needed)

**Selected**: ___________

**Rationale**: 
___________________________________________
___________________________________________
```

---

## 如果数据不足怎么办？

### 情况A: 没有专家的daily returns

**解决方案**: 用已有的model_summary作为粗略估计

```python
# 粗略方法：用median_annret作为proxy
df = pd.read_csv('model-test/outputs/full_us_deans_60/model_summary.csv')
experts = df[df['model_id'].isin(core_experts)]

# 假设不同专家如果median_annret相近，则策略相似
# 计算annret的"距离"作为相似度的逆
from scipy.spatial.distance import pdist, squareform

features = experts[['median_annret', 'median_sharpe', 'median_maxdd']].values
distances = pdist(features, metric='euclidean')
similarity = 1 / (1 + squareform(distances))

print("Expert similarity (based on aggregate metrics):")
print(pd.DataFrame(similarity, 
                   index=experts['model_id'], 
                   columns=experts['model_id']))
```

### 情况B: 没有adaptive_router的单独数据

**解决方案**: 
1. 查看现有Streamlit的单股workflow，adaptive_router是默认选项
2. 或者快速跑一次adaptive_router回测：

```bash
# 临时脚本
python -c "
from core.adaptive_regime import AdaptiveRouter
from core.backtest import simulate_strategy
import pandas as pd

# 加载一只测试股票
symbol = 'AAPL'
df = pd.read_parquet(f'data/stocks/{symbol}.parquet')

# 运行adaptive_router
router = AdaptiveRouter()
signals = router.generate_signals(df)
result = simulate_strategy(df, signals)

print(f'Adaptive Router on {symbol}:')
print(f'  Sharpe: {result.sharpe_ratio:.3f}')
print(f'  Ann Return: {result.annual_return:.3f}')
print(f'  Max DD: {result.max_drawdown:.3f}')
"
```

---

## 下一步

根据Phase 0结果：

### 如果决定STOP
```bash
# 归档Phase 0报告
git add document/phase0_reports/
git commit -m "docs(phase0): expert system audit complete, no reconstruction needed"

# 更新路线图
echo "Phase 0 Decision: STOP (adaptive_router sufficient)" >> document/expert_system_reconstruction_roadmap.md
```

### 如果决定继续
```bash
# 进入Phase 1
cd document
echo "Phase 0 Decision: PROCEED to Phase 1" >> expert_system_reconstruction_roadmap.md

# 创建Phase 1分支
git checkout -b expert-system-reconstruction-phase1

# 开始Phase 1第一个任务
# 见 document/expert_system_reconstruction_roadmap.md Phase 1.1
```

---

## 常见问题

**Q1: 如果full_us_deans_60数据不全怎么办？**

A: 可以用更小范围快速验证：
```bash
# 只用10只股票快速跑
python model-test/quick_expert_audit.py --symbols AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,V,JNJ --days 252
```

**Q2: 相关性分析需要多长历史？**

A: 至少252天(1年)，理想是504天(2年)。如果数据不足，Phase 0结论不可靠，建议直接进Phase 1。

**Q3: Phase 0发现adaptive_router很好，但我还是想尝试改进可以吗？**

A: 可以，但要明确：
- 你在追求**边际改进**（+5-10% Sharpe）
- 而非**根本性问题修复**
- 成本/收益比可能不划算
- 建议: 如果Sharpe > 0.8，投入时间到其他项目更值

---

**预计时间**: 
- Step 1-2: 30分钟
- Step 3: 1-2小时（如果需要重跑回测）
- Step 4: 30分钟（分析决策）

**总计**: 半天到1天

开始执行吧！有问题随时问我。
