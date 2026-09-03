# Stage: Deck Projection（幻灯片投影）

## 输入

- `narrative/narrative.yaml`（已过 Gate 2）。
- `brief/brief.yaml`：受众、takeaways、硬约束、spec.dimensions。

## 你做什么

把同一个 story 投影为 `projection/deck_plan.yaml`。**这是投影，不是压缩**：报告的
写法和你无关，你只对"现场这 30 分钟观众怎么被带走 message"负责。

页面规则：

- **语域：deck 是说出口的话。**短句、可念、口语节奏——和报告的书面语不是一档；
  brief.voice.deck 可覆盖全局风格。听的人只有一次机会，读的人可以回头。
- 一页 ≈ 一个主要沟通信息。内容页 `title` 写**观众该记住的那句话**，不写话题所属。
  反例："实验结果"。正例："Cache Partitioning 将 P99 latency 降低 18.2%"。
- **说人话（默认规则，最大的质量问题）**：标题和要点用"做了什么 / 观察到什么 /
  结果是什么"的直白句式，念出来要像在会议上说话。诊断密码句的信号：一句话里
  术语超过两个、出现"即""载体""表征"这类压缩词、或砍掉所有动词。
  差（密码句）："平坦即证据：非重叠臂<3皮秒的完全平坦，证明效应载体是容量重叠"。
  差（AI 味金句）："伤害来自缓存共用——分开，就没事"。
  好："两条链路完全分开后，干扰没有再出现；瓶颈确认是容量共用"。
  **AI 味禁令**（校验器会抓）：①破折号金句"陈述——短句"，标题和结论条里一条
  都不要有；②比喻拟人（伤害/立尺子/靶点/组合拳…），直说技术事实；③"不是X，
  而是Y"对仗句每页最多一次。直白≠修辞：不需要比喻、不需要类比、不需要金句，
  主谓宾+数字就是最好的直白。术语首次出现给半句白话即可。
  **brief.voice 优先于本段默认纪律**：Gate 1 选定的风格档和 `voice.rules`
  （如 punchy 场景 relax em-dash）才是本 run 的标准。`comh validate` 的
  style:* findings 按 brief.voice 执行，驱动改写循环：改写或有理由地保留 warn；显式禁词 error 必须修复。
- 可选 `kicker`（页眉小标，如"结果 · RESULTS"）：小号强调色，提供编辑级层次；
  不要重复标题内容，每个 section 用一次即可。
- 但不要机械执行：`page_role` 为 `cover` / `agenda` / `section_divider` /
  `closing` / `appendix` 的页面用主题式标题是正当的。系统按 role 理解页面，QA 也按
  role 分规则检查。
- `beat`：引用 `Sxx`。一 beat 拆多页可以；多 beat 并一页写 `beats: [Sxx, Syy]` 与 `merge_rationale`。
  本媒介不呈现的 beat，在计划顶层登记 `omissions: [{beat, reason}]`。

## 让页面充实（展开结构）

"三个短 bullet 孤悬一页"就是太空。页面主体区至少要有一种展开结构或视觉块：

- **`support_points` 支持 `{point, detail}`**：point 是加粗导语，detail 是下面一行浅色
  展开。这是首选的充实手段——比加第四第五个 bullet 好，信息有层次。
- **`metric_cards`**：数据页的大数字卡片，`{label, value_from: Exxx}`，数值渲染时从
  evidence 取（不会漂移）。适合 2-4 个关键数字。卡片和图表同时用会很挤，二选一。
- **`callout`**：底部"so what"结论条 `{text, evidence?}`。**强化本页信息，不许引入
  第二个 message**——如果 callout 讲的是新事情，说明该拆页了。
- `visual.intent`：用自然语言描述视觉意图，具体像素留给 renderer。落到具体载体时：
  - **数据图优先用 `visual.chart`**：`{type: bar|column|line, series: [{label,
    value_from: Exxx}]}`。数值在渲染时直接从 evidence 的 `value.number` 取——图上的
    数字物理上不可能和证据库漂移。前提：被引用的 evidence 条目必须有 `value`。
  - **示意图用 `visual.diagram`**：`{mermaid: <flowchart 源>, caption, evidence?}`。
    mermaid 经编译器的确定性布局链（真实字体测量、碰撞校验）编译成 PNG，按内容哈希
    缓存。当前只支持 flowchart/graph 子集（subgraph、sequence 等会失败）——
    `comh validate` 会干跑图语法，错误在验证期就报出来。渲染需要 draw.io CLI
    （`DRAWIO_CLI` 指向 draw.io Desktop）。
  - 已有图片用 `asset_refs`，**引用图片时用对象形式 `{ref, caption, evidence}`**——
    caption 随图渲染，evidence 把图挂进溯源链。图不是溯源的盲区。

密度仍按 brief 的 spec.dimensions 判断——没有死字数规则，但"空"和"密"都该是有意
为之的选择，不是默认结果。
- `deck.style`：`template` 选主题（内置五个方向见下表，未知名字回退默认并出
  finding）；`transition` 选转场（`fade|push|wipe|cut`）；其余键（如
  `palette_hint`）自由写，代码透传。注意：brief 禁深色时选暗色主题会被校验器
  打回、渲染器强制浅色——硬约束赢。
- `notes`：演讲备注是一等内容。被你从页面上拿掉的细节、过渡话术、预备的问答，写进
  notes。
- `demotions[]`：凡是从本 beat 里裁掉、去了别处的信息，登记 `{content, to}`，
  `to` ∈ `notes | appendix | report_only`。**内容去向必须可审计**——没有 demotion
  记录的静默丢弃会被 QA 盯上。
- `emphasis` / `reveal`：**出场顺序和强调是沟通决策，不是视觉决策**——这是动画的
  语义建模（fragment 模式）。正式形式是步骤对象：
  ```yaml
  reveal:
    - elements: [support_points[0]]   # 语义地址：title | callout | visual |
      verb: fade_in                    #   support_points[i] | metric_cards[i]
      trigger: click                   # 动词: appear|fade_in|emphasize|highlight
    - elements: [visual, callout]      # 触发: click|with_previous|after
      verb: fade_in
      trigger: click
  emphasis:
    - elements: [title]
      verb: highlight
  ```
  纯字符串仍然允许（自由备注，renderer 忽略）。地址在 validate 期确定性解析——
  写错名字/越界会直接报 error。**HTML surface（`comh render deck-html`）已执行这份
  语义**（reveal.js fragment：出场顺序/点击步进/强调高亮）；PPTX 通过实验性动画开关执行同一份语义，默认关闭；须在实际播放器核验。
- 所有数字必须来自 evidence（派生数字先落库，见 stages/evidence.md）。

- **版式原型（`page_role` 扩展）**：
  - `content`（默认）：标准上下/双栏图文排版。
  - `hero_split`：左图右文或左文右图 Hero 分栏，图文顶格等高。
  - `fullscreen_backdrop`：全幅背景图 + 居中悬浮半透明卡片（`backdrop_card`），沉浸式叙事。
  - `timeline`：横向里程碑时间轴（推荐 3-4 节点，超出出 warning），带步骤徽标与展开要点。
  - `versus`：双栏并列对比（如基线 vs 优化）。列名由 `visual.columns: [左列名, 右列名]` 给出——渲染器不发明文案，缺失时降级为裸 A/B 并出 warning。

- **背景图与蒙层（`visual.background`）**：
  - 语法：`visual.background: {asset: "assets/hero.jpg", opacity: 0.15, overlay: theme|frosted-glass}`
  - **实测保底与素材铁律**：背景图必须在 `assets/manifest.yaml` 登记溯源；系统使用 PIL 实测 worst-case 对比度，不足 4.5:1 时动态步进 α 蒙层（封顶 0.90），保证文字绝对清晰。HTML 支持毛玻璃，PPTX 自动优雅降级为实色半透明矩形。

- **样板先行与局部精细微调工作流（对话协议）**：
  1. **样板对齐（Specimen Preview）**：先对齐整套粗大纲，再细化典型的 Cover 与 Content/Hero 页，用 `comh render deck-html --preview` 渲染当前草案。保留其他页的结构和 beat 覆盖，可展示典型页供用户看风格。预览不产生交付凭据；用户已选定成熟主题或明确要求直接出稿时可直接细化全套。
  2. **精准单页微调（Surgical Page Tuning）**：成品生成后，当用户指出某页（如 P03）某部分需要调整时，直接针对该页 `Pxx` 的字段（如版式 role、要点措辞、背景透明度、卡片数据）进行手术式修改并重新校验渲染，绝不破坏其他页面的既有结构。

## 样式方向：选型或生成（对话式，不只是学术汇报）

风格是数据（`themes/<name>/theme.yaml`，色板/字体/字号），没有代码。内置方向
是**起点和兜底，不是天花板**——气质没被命中时，你现场创作一套（见下）。内置
五方向：

| 方向 | 气质 | 适合 |
|---|---|---|
| tier1-light | 干净留白、蓝笔标注 | 学术汇报、评审 |
| slate-tech | 浅石板底、靛蓝 | 客户技术评审 |
| midnight | 深色舞台 | 大屏发布、路演 |
| poster-pop | 奶油纸+朱红+超大字 | 创意提案、发布周、需要被记住的场合 |
| gallery-noir | 暖黑+象牙+鎏金衬线 | 颁奖、作品集、周年叙事 |

对话协议（**用户只说人话；配置是你的落笔处，不是用户的作业**）：

1. 用户描述感觉（"要酷一点""像杂志""要吸睛"）→ 先看内置方向是否命中：命中
   就提 2-3 个候选，每个一句话气质+适用场合，**不甩配置名**；用户犹豫就渲染
   对比版让他挑（换 template 重渲染，浏览器里翻着看）。没命中 → 走生成。
2. 口头微调（"标题再大""强调色暖一点"）→ `tokens_override` 落一层重渲染。
3. **沟通纪律：对用户说"页/版本/感觉"，不说 YAML、命令、文件路径**。底层
   落点是审计记录，用户要看时再展示。
4. 硬约束赢：brief 禁深色时暗色主题会被强制回浅色（确定性），别推荐会被打回
   的方向。

### 生成式主题：现场创作一套（AI 创造力的正门）

用户的气质诉求没有现成方向命中（"赛博霓虹""水墨留白""编辑部分栏感"），或明说
"给我定制一套"——**不要硬凑内置主题，当场创作**：

1. **推导设计决策，讲人话**：底色与光感怎么定、主色和强调色什么关系（互补/
   同色相深浅/高饱和撞色）、字号比例尺戏剧化还是克制、中西字体怎么配对。给
   用户听的是设计理由，不是色号。
2. **落成数据**：写 run 级 `themes/<气质名>/theme.yaml`（纯 token，renderer
   自动发现）。这就是全部——主题没有代码，生成主题不需要工程。
3. **过体检**：`comh validate` 对生效主题做确定性检查——正文/背景对比度
   ≥4.5:1（error，不过关**不许渲染**）、muted 与强调色 ≥3:1（warn）、
   `is_light` 不许与实际底色不符、字号不许低于可读下限。不过就改到过关：
   **创意不许以看不清为代价**。
4. **样张对齐**：渲染 1-2 页（cover + 一页带卡片/图表的 content）给用户看；
   口头迭代（"再暗一点""金色收一点"）直接改 theme 再出。满意后整套贯穿
   pptx/html/报告三端。

边界要如实：风格词汇 = 色板/字体/字号/构件选择，自由像素布局永远不开放
（溢出保证是底线）。用户要的效果超出词汇表时：先试 token 组合 → 再试生成新
主题 → 还不够就明说"当前版式引擎做不到"，不要硬凑。结构类的新视觉（装饰
元素、密度、布局变体）走 renderer 侧长词汇，双表面同步实现——那是工程任务，
不是你当场能写出来的。

## 素材：对话、检索与落地（三铁律）

装饰照片、插画登记素材出处；承载事实的图表/截图按 evidence 阶段提取，不能混为装饰。
图的含义靠 `asset_refs` 的 `{ref, caption,
evidence}` 挂接（caption 讲这是什么，evidence 挂它支撑的论断）。

三铁律（校验器抽查登记，协议靠你执行）：

1. **先同意，后联网**。任何网络检索素材前先问一句，拿到明确同意再动手；同意
   在本 run 内持续有效，用户可随时收回。绝不静默检索。
2. **落盘 + 登记**。素材下载进 `runs/<name>/assets/`（绝不热链），并在
   `assets/manifest.yaml` 登记 `{file, origin_url, license, fetched_at, note}`。
   渲染只读本地文件——离线、确定性、可复现。校验：登记的文件不在盘上 =
   error；页面引用了没登记的素材 = warn；用着素材却没有 manifest = info。
3. **许可优先**。公有领域 / CC 素材优先（Wikimedia 常是好来源）；许可不明就把
   风险讲给用户、让用户拍板，不要先斩后奏。

对话协议（用户问"我想展现 X 的成长历程，需要什么素材？怎么呈现比较好？去检索
一下？"）：

1. **先提案，后动手**：呈现方式（时间线 = `visual.diagram` mermaid 或分节
   support_points + 老照片 `asset_refs`；里程碑 = metric_cards + 大图）+ 素材
   清单（每张：年代/内容/为什么值得放）+ 建议来源。用户点头才检索。
2. 检索 → 落盘 → 登记 → 引用 → 重渲染。
3. **出版本对齐**：同一页出 1-2 版（"这版双栏时间线+照片墙，那版单线大图"）
   让用户挑，不要来回猜。

## 收尾

```
comh save deck_plan
```

narrative 或 brief 之后有任何变更，deck_plan 自动标脏，需要重新投影。
