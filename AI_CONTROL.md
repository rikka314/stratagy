# AI Control Guide

> 面向对象：项目维护者、协作者
> 用途：指导人如何在这个仓库里更高效地使用 AI，而不是指导 AI 如何读仓库。

## 1. 这份文件是干什么的

这个项目已经从“让 AI 每次先扫全仓找接口”切换成“先选任务边界，再按需读取接口文档”的协作方式。

你的目标不是一次性把所有上下文都塞给 AI，而是：

1. 先判断任务属于哪个模块
2. 让 AI 只读对应的 skill 和接口文档
3. 只在跨域任务里再扩展上下文

这样可以明显减少上下文浪费，也更容易让 AI 连续几轮都保持稳定。

## 2. 默认工作流

每次发任务，优先按下面顺序来：

1. 先选一个最接近的 skill
2. 再补一句任务目标
3. 如果任务不清楚，先让 AI 做接口对齐
4. 只有跨域任务，才让 AI 扩展到第二个 skill 或第二份接口文档

推荐口令模板：

```md
用 <skill名> + <任务目标>
```

例如：

```md
用 strategy-single-stock-workflow 检查 current_artifact 是怎么提交到结果区的
```

## 3. 什么时候用哪个 skill

| 场景 | 推荐 skill | 典型任务 |
|---|---|---|
| 不知道接口在哪 | `strategy-interface-alignment` | 找入口、找调用链、找状态键、判断该交给谁做 |
| 改页面、图表、导出、视觉 | `strategy-frontend` | 首页、入口页、分析页、共享图表、HTML 导出 |
| 改数据/指标/信号/回测/评估 | `strategy-core-pipeline` | 改信号列、回测逻辑、评估指标、搜索逻辑 |
| 改单股工作流 | `strategy-single-stock-workflow` | `StrategyRequest`、artifact、stage cache、lineage、结果板 |
| 改多股分析和组合 | `strategy-multi-stock` | 股票池、组合模拟、市场上下文、多股结果区 |
| 改部署 | `strategy-deploy` | `/strategy` 子路径、Nginx、上传脚本、systemd |

## 4. 最推荐的发指令方式

### 方式 A：显式点 skill

这是最稳的方式，推荐优先用。

示例：

- `用 strategy-interface-alignment 找单股页面策略生成的入口、输入和输出`
- `用 strategy-frontend 调整多股结果区图表布局，但不要改底层组合逻辑`
- `用 strategy-core-pipeline 检查 compute_signals 的输出列有没有影响到单股 workflow`
- `用 strategy-deploy 检查 /strategy 子路径部署链路`

### 方式 B：纯自然语言

也可以，但命中不一定总是最稳，尤其是在刚创建新 skill 的当前会话里。

示例：

- `帮我找单股 workflow 的 artifact 链路`
- `看看多股组合结果区的数据是从哪里来的`
- `检查部署脚本和 nginx 子路径配置`

建议：

- 新开会话后，可以更放心用纯自然语言
- 当前会话里，最好直接点 skill 名

## 5. 怎么写提示词最省上下文

好提示词的结构：

1. 指明 skill
2. 指明目标
3. 指明边界
4. 指明交付物

模板：

```md
用 <skill名> <做什么>
边界：<不要碰什么 / 只看什么>
交付：<要改代码 / 要给分析 / 要给结论 / 要列接口>
```

例如：

```md
用 strategy-multi-stock 检查多股结果区的 portfolio_result 是怎么被消费的
边界：只看多股页和组合模块，不要回扫单股 workflow
交付：列出入口文件、关键函数、输入、输出、影响范围
```

## 6. 哪些说法会让 AI 浪费上下文

尽量避免：

- `先把整个项目都看一遍`
- `先找出所有接口`
- `把相关代码全读了再说`
- `从头分析整个系统`

这些说法很容易让 AI 在真正做事前就把上下文花掉。

更好的说法是：

- `先找这个功能的入口和上下游`
- `先确认这个页面依赖哪些接口`
- `只看单股 workflow，不要扩展到多股`
- `先定位状态键和调用链，再决定是否改代码`

## 7. 遇到不确定任务时怎么发

如果你还不知道该叫哪个 skill，就先这样发：

```md
用 strategy-interface-alignment 帮我定位这个任务应该落在哪个模块
我要做的是：<一句话描述>
交付：给我入口文件、关键函数、输入、输出、影响范围、建议转交的 skill
```

这是默认兜底入口。

## 8. 推荐的任务拆分方式

### 小任务

适合直接给一个 skill：

- 改一个页面
- 改一个图表
- 改一个状态键
- 改一个策略阶段
- 查一个调用链

### 中任务

先接口对齐，再转具体 skill：

1. `strategy-interface-alignment`
2. `strategy-frontend` / `strategy-single-stock-workflow` / `strategy-core-pipeline` / `strategy-multi-stock` / `strategy-deploy`

### 大任务

拆成连续的几轮，不要一轮里要求：

- 找接口
- 改代码
- 跑验证
- 写总结

建议拆成：

1. 接口定位
2. 实现
3. 验证
4. 收口说明

## 9. 什么时候适合用别的 AI

当前项目建议：

- Codex / Claude 类强代码代理：
  适合跨文件实现、调试、接口边界梳理、架构修改
- DeepSeek：
  适合中文文档、说明文案、轻量单文件改写
- GPT-5：
  适合第二意见、方案验证、英文资料总结
- Gemini：
  适合超长文档快速阅读

原则是：

- 高价值、跨文件、要保持上下文一致的任务，用主代理
- 轻量写作和资料整理，可以外包

## 10. 推荐的常用指令模板

### 找接口

```md
用 strategy-interface-alignment 找 <功能名> 的入口、输入、输出和影响范围
```

### 改前端

```md
用 strategy-frontend 做 <页面/图表/导出任务>
边界：不要改底层策略逻辑
```

### 改单股工作流

```md
用 strategy-single-stock-workflow 做 <artifact / stage cache / lineage / 结果板任务>
```

### 改策略链路

```md
用 strategy-core-pipeline 做 <数据/信号/回测/评估任务>
边界：不要动 UI
```

### 改多股组合

```md
用 strategy-multi-stock 做 <股票池 / 组合模拟 / 市场上下文 / 结果区任务>
```

### 改部署

```md
用 strategy-deploy 检查或修改 <部署任务>
边界：只看 deploy、config 和路由相关文件
```

## 11. 一句话规则

- 明确任务：直接点 skill
- 不明确任务：先接口对齐
- 能缩小边界就缩小边界
- 不要让 AI 先扫全仓
- 一轮只解决一类问题
