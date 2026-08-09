# Frontend Style Standard

> 生成日期：2026-03-27；首页方向更新：2026-08-06
> 状态：W6-W8 前端唯一风格基线
> 适用范围：`/strategy`、`/strategy/stock-analysis`、`/strategy/stocks-analysis`、后续单股/多股主分析页、共享图表容器、导出 HTML
> 参考逻辑：学习官网产品页的结构语法与页面节奏，不复制任何外部品牌内容
> 优先级：如与 `document/UI_DESIGN_GUIDE.md` 或旧前端规则冲突，以本文件为准

## 1. 目标

W6-W8 前端不再沿用“给 Streamlit section/card 上皮肤”的思路，而是切到“正常网站式产品工具页”的思路。

当前冻结方向：

- 暖白、米白纯净背景，不做整页格子纹理，不再使用蓝灰 paper-card 学术风作为主视觉
- 轻 header：品牌左侧、主路由居中、证据入口与语言切换右侧；导航无胶囊外框
- 首页采用固定平台标题、动态新闻小字、强势股票星图与三幕市场镜头；入口页继续采用 `左操作 / 右展示` 的 split-layout
- 页面里只保留少量真正必要的 surface，不再制造卡片墙
- 推荐列表改成单个白色 sheet 内的轻量行列表，小按钮化，不再是一排排大卡片
- 普通提示、空态说明、辅助文案尽量走普通文字和轻分隔，不再给每段话套一个框
- 共享静态 HTML 必须走稳定渲染路径，不允许再出现标签被直接打印到页面上的情况

## 2. 页面语法

W6-W8 页面默认遵循：

入口页与分析页默认遵循：

`light header -> intro / hero -> split layout -> single action card + single showcase board -> supporting text`

首页采用独立语法：

`light header -> single viewport-scale market lens stage`

解释：

- `light header`：站点级导航壳层，负责品牌、主路由、研究证据入口与语言切换
- `intro / hero`：一句话说明页面在做什么，不写开发进度
- `split layout`：左侧主叙事或主操作，右侧单个大展示区
- `single action card`：页面里唯一的核心交互 surface
- `single showcase board`：页面里唯一的核心上下文展示 surface
- `supporting text`：底部少量补充说明，用轻分隔处理，不回退到 section/card 堆叠

## 3. 视觉系统

### 3.1 背景与层级

- 背景使用暖白或米白主色，允许柔和光晕或轻渐变，但不要整页网格
- 页面主体更像官网产品页，而不是分析后台或实验面板
- 主内容层级只允许三层：
  1. 页面壳层
  2. 主 surface（action card / showcase board）
  3. 内部轻量 sheet / 行列表 / 状态行

### 3.2 Surface 规则

- 不允许整页出现大面积圆角大白卡把所有内容包起来
- 入口页的重心应该明显落在 1 个 action card 和 1 个 showcase board 上；首页不使用这两类 surface
- showcase 内可以有少量白色 sheet，但必须是稳定排布，不能靠绝对定位乱叠制造层级
- 边框密度要低，主要靠留白、排版、轻分隔建立层级

### 3.3 Token 方向

必须提供并优先复用这些语义 token：

- 背景：`bg-canvas`、`bg-glow`
- Surface：`surface-main`、`surface-sheet`、`surface-frost`
- 文本：`text-strong`、`text-primary`、`text-secondary`、`text-muted`
- 线条：`surface-line`、`surface-line-strong`
- 强调：`accent-primary`、`accent-warm`
- 状态：`accent-positive`、`accent-warning`、`accent-danger`

页面实现只能走 token，不允许散落硬编码颜色。

### 3.4 Header 规则

- header 必须轻、薄、单行优先，看起来像网站导航，不像后台总控栏
- 结构固定为“左侧品牌 / 居中主路由 / 右侧证据入口与语言切换”
- 首页、单股、多股、报告位于视觉正中；“浏览研究证据”紧邻语言切换
- 所有顶部选项保持无边界，不使用胶囊外框；active 态只依靠文字颜色与字重
- 不做整条厚重导航盒，不做额外的第二层导航壳
- 桌面端优先保持单行对齐，窄屏允许自然换行，但不能出现品牌和导航互相挤压

### 3.5 CSS 加载结构

- `ui/theme.py` 保持单一主题源，通过 selector 编译为 `base / home / entry / analysis / report` 五个 bundle
- 每条真实路由只注入 `base + 当前页面 bundle`；不得恢复所有路由共用完整 style block 的加载方式
- `base` 只承载 token、站点壳、header、共享控件和响应式基础；首页动画、分析结果板、原生报告 reader 必须留在对应 bundle
- `inject_global_styles()` 仅作为旧调用兼容入口；新 route wrapper 必须显式使用 `inject_base_styles()` 和自己的 route bundle
- 删除 selector 前必须先用源码检索和浏览器 DOM 核验消费者，不能根据类名推测是否废弃

## 4. 首页规范

首页必须是一眼看上去像克制的市场研究产品封面，而不是 Streamlit dashboard。

首页只保留：

- 轻 header
- 固定平台标题：“股票策略分析平台”（英文为 `Stock Strategy Analysis Platform`），使用中等字号并保持单一视觉焦点
- 平台标题下方只保留一行小号新闻，使用轻微上跳与淡入淡出轮换；长标题单行截断，不重新撑高首页
- 标题与市场镜头之间放置“强势股票星图”：中央以公司名为主、代码和涨跌幅为辅，并展示真实近 20 个交易日日 K；外围错落展示同市场相对领先项的公司名、代码和涨跌幅，位置按日期和当前股票稳定重排，避免每次 rerun 抖动
- 星图使用真实 Streamlit 按钮切换 `美股 / A 股` 和“换一只”；按钮与星图必须位于同一个相对定位容器并随页面同步滚动，移动端只保留两个外围股票，按钮不得与下方市场镜头重叠
- 一个无边界三幕市场镜头：依次轮换地区指数、固定高流动性观察池的日内领先标的、由指数广度/平均涨跌/离散度归纳的市场温度
- 指数、观察池报价和中央股票日 K 由服务端行情接口拉取并按 15 分钟缓存；接口失败时只显示“待更新”或“K 线暂不可用”，不得使用伪造数据补位
- “观察池日内领先”必须明确样本边界与非投资建议属性，不得写成全市场最佳或买入推荐

首页不再保留叙事说明、action card、showcase board、支持说明三栏或正文 CTA。单股、多股、报告与研究证据入口全部由顶部导航承担。

首页动画必须低频、平滑；新闻只允许小幅上跳，不能带动平台标题或页面布局。三幕切换使用连续交叉淡化，交界处不允许完全空白。`prefers-reduced-motion` 下固定显示第一条新闻与第一幕指数快照。

## 5. 入口页规范

单股入口页和多股入口页必须属于同一视觉系统。

### 5.1 统一结构

- 顶部轻 intro
- 左侧一个主 action card
- 右侧一个大 showcase board

### 5.2 主 action card

单股入口页内包含：

- 市场切换
- 搜索
- 搜索结果选择
- 开始分析按钮
- 上传区域

多股入口页内包含：

- 市场切换
- 搜索加入
- 上传多个 CSV
- 已选股票管理
- 开始多股分析

规则：

- 左侧不再把每个子区块再包成独立大边框卡
- 通过 section 标题、分隔线、稳定间距组织内容
- 正常空态信息使用 caption 或轻说明，不做大提示框

### 5.3 Showcase board

右侧 showcase board 统一包含：

- 市场快照
- 推荐股票 sheet

规则：

- 市场快照可以是轻量指标块，不需要再额外做厚重卡片组
- 推荐股票必须落在单个白色 sheet 中
- sheet 内部使用等高轻量行列表
- 行结构是左侧文本、右侧小按钮
- 文字块与右侧按钮必须垂直居中对齐，不能出现文字两行但按钮顶在上面的情况
- 按钮不横向撑满，不做表单系统大按钮
- 列表允许固定高度滚动

### 5.4 多股已选列表

- 不再用沉重的表格和框中框
- 优先使用轻量行列表或表格式 row 管理
- 每行只表达代码、来源/说明、操作

## 6. 交互与状态规则

### 6.1 按钮

- 主 CTA 可以较强，但仍属于产品页按钮，不是后台按钮
- 推荐区和已选列表区按钮必须明显更小
- 不允许用默认 Streamlit 蓝按钮作为最终视觉
- 文字型链接和导航项不要使用下划线作为主交互提示

### 6.2 状态提示

- loading、empty、error、missing field 都要定义
- 中性辅助说明默认走普通文字
- warning / error 允许做轻量状态行，但不要重新回到大框提示

统一空态文案基线：

- `正在加载最新市场数据`
- `没有找到匹配股票`
- `暂无数据`
- `暂时无法获取推荐股票`
- `暂无可展示结果`

### 6.3 HTML 与 Streamlit 实施细则

- 大块静态 HTML 默认走共享 `render_html()` 包装，不要直接写大段 `st.markdown(..., unsafe_allow_html=True)` 作为主要渲染路径
- 当前项目中，`render_html()` 应优先使用 `st.html()`，避免 markdown 规则把标签直接打印到页面上
- 小型内联 HTML 可以继续使用 `st.markdown(..., unsafe_allow_html=True)`，但必须保持短小、单层、无复杂嵌套
- 行列表、推荐列表、已选列表这类 `st.columns` 布局必须额外检查纵向对齐，确保文本和按钮在同一个视觉中线

### 6.4 共享实现归属

- `ui/theme.py` 是当前前端共享系统的唯一主题入口，负责 token、背景、header、split-layout、action card、showcase board、floating sheet、row list、小按钮等共享语义
- `ui/home.py`、`ui/single_stock_entry.py`、`ui/multi_stock_entry.py` 优先组合共享样式与共享 HTML 结构，不要各自复制一套 page-local CSS
- 新增布局语义时，先判断是否属于站点级共性；如果是，先沉淀到 `ui/theme.py`
- 页面文件应该主要描述内容结构和数据映射，不应该再次定义另一套颜色、圆角、阴影和间距体系

## 7. 实施约束

- 不改 `/strategy`、`/strategy/stock-analysis`、`/strategy/stocks-analysis` 的路由语义
- 不改单股与多股入口页的返回 payload shape
- 不改 `core/market_context.py` 返回数据 shape
- 不改 W5 workflow、`strategy_workspace`、artifact 与分析页主链路
- 允许使用共享 HTML/CSS 完成静态展示区
- 允许隐藏 Streamlit 默认顶部菜单和顶栏，让页面更像网站
- 新增共享 HTML/CSS 能力时，优先沉淀到 `ui/theme.py`，不要在页面文件里各自再长一套局部实现

## 8. 反模式

以下内容视为当前阶段明确反模式：

- 页面满是大框、大卡片、大面板
- 整页铺网格背景
- 顶部做成厚重导航盒
- 顶部导航项靠下划线做 active 态
- showcase 内小卡依赖绝对定位互相压叠
- 首页或入口页继续沿用 Streamlit section/card 堆叠
- 首页重新加入说明卡、研究流程板或底部说明栏
- 推荐项一条条独立大卡片
- 推荐按钮和列表操作按钮横向撑满
- 推荐行或已选行里，按钮和文本不在同一个垂直中线上
- 大段 HTML 通过 markdown 被当成普通文本打印出来
- 普通说明文案被塞进提示框里
- 蓝灰 paper-card 拼贴感重新回到首页与入口页

## 9. 完成标准

符合本标准的页面应满足：

- 首页一眼看起来像官网产品页，而不是分析后台
- 首页、单股入口、多股入口通过同一 token 与顶部导航保持同一设计系统
- 单股与多股入口的左操作右展示成立
- 交互重心清楚落在一个主 action card 上
- 入口页的上下文重心清楚落在一个主 showcase board 上
- 首页新闻轮播、强势股票星图与三幕市场镜头稳定运行，平台标题始终清晰可读
- 推荐列表已经变成轻量行列表 + 小按钮
- 行列表中的文字和按钮始终垂直对齐
- 桌面与移动端都不出现按钮挤压、控件重叠和层级失控

## 10. 前端回归清单

每次完成首页、入口页或共享主题层改动后，至少逐项确认：

- 背景仍然是暖白/米白纯净底，不存在整页格子纹理回退
- header 仍然是轻量无边界网站导航：品牌在左、四个主路由居中、证据与语言在右
- 首页仍然只有固定平台标题、新闻轮播、强势股票星图与三幕市场镜头；入口页继续保持“左操作 + 右展示”的 split-layout
- 入口页重心仍然落在一个主 action card 和一个主 showcase board 上
- 首页地区指数、观察池领先项和市场温度均有可解释口径；行情失败时安全降级为“待更新”
- 首页“换一只”和“美股 / A 股”按钮必须真实更新星图状态，不能只做视觉按钮
- 推荐列表和多股已选列表仍然是单个 sheet 内的轻量行列表，不是独立大卡片堆叠
- 行列表右侧按钮尺寸受控，且与左侧文本垂直居中对齐
- 大块 HTML 没有以原始标签文本形式出现在页面上
- 链接、导航项、文字按钮没有重新出现难看的下划线
- 新增样式优先沉淀在 `ui/theme.py`，没有在页面文件里长出第二套视觉系统
