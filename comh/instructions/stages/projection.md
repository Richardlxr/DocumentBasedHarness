# Stage: Projection（先对齐大纲）

输入是已确认的 brief 与 narrative。先 `comh next --json`；故事线仍在等待回复时停止投影。

按所选媒介起草 deck_plan/report_plan：只先确定页或节的职责、顺序、标题、beat 覆盖与取舍。
大纲由这些字段生成，不额外维护一份 outline.md。报告和演示稿可以有不同展开顺序。
草案仍需满足 schema 和引用规则；暂缺的内容不可冒充已完成的正文。
演示稿使用 context 中的 presentation_profile。学术默认充分展开，同一主旨可有多组
证据和解释；先对齐内容职责，再参考分组、主图配解释、结论与条件相邻等布局建议。
不把字数目标、卡片位置或 preset 字段写入 narrative。大纲阶段不按正式正文密度评判草案。
研究/技术汇报先按 [研究展示](../references/research-presentations.md) 检索来源中的架构、
对照、实验过程与故障成因，确认哪些进入正文。用页面职责连接目的、机制与证据，
不把“验证通过”当成所有页面的主旨；机制页允许准确的主题标题。

大纲阶段就为每页选载体或文字形态（`visual.arrangement` / `visual.table` 等），依据是
页内信息关系而不是轮换样式；present 视图的 carrier 会显示 `text:steps` 等形态，整套都是
`text` 时先自查再给用户看。

保存对应计划，执行 `comh present deck_outline` 或 `comh present report_outline`。
用人类可读的结构给用户看，附重要取舍，等待回复。按 [对话协议](../references/dialogue-protocol.md)
记录接受、修改或委托；present 的输出只代表待确认，不能自行填回复。

- checkpoints：粗大纲接受后自主细化。
- collaborative：先对齐粗大纲，再每次处理一个页/节，按“职责与顺序 → 要点和证据 → 细节”推进；
  当前页/节完整后 `comh present deck_detail --node P01` 或 `report_detail --node R01`，记录用户回复。
  所有所选页/节完成对齐或明确委托后，才能正式渲染或保存报告正文。
- delegated：仍展示粗大纲，用户可以回复明确委托；记录 delegated，不能伪装成已审阅具体内容。

PPTX 粗大纲接受后、批量细化前，处理样式模板：先看 `brief.appearance` 和 `comh next`。
若有模板合集/未定选择，展示少量候选供选择；已明确指定单个模板不重复询问选择。
首次原生 PPTX 模板适配，先制作代表性的封面与内容页样张，说明保留元素和重要简化，
`comh render deck --preview` → `comh present deck_appearance`，展示真实 PPTX 渲染与差异，
收到实际回复后记录接受或明确委托。没有当前样式接受时 CLI 禁止正式渲染与逐页 detail 接受。
用户在 Gate 1 明确委托样式选择/审阅时可省略此轮；委托大纲细化不能代替样式授权。
同一 run 内样式未变的后续内容编辑沿用接受记录。样式更换使该记录失效，但不要求重审故事线。
意外换行等恢复既定效果的缺陷直接修复并重新 QA；品牌删改、字体替换等重要调整要说明。
具体契约与兼容性检查按需读 [PPTX 样式模板](../references/pptx-style.md)。

用户可随时调整协作档位。拒绝的方向、当前请求及回复留在 run.yaml，恢复后先读取。
修改大纲结构会使其确认失效；只改变主题、字体等样式不会改变粗大纲的结构指纹。

到具体 authoring 再读 [deck](deck.md) 或 [report](report.md)，不提前加载全部视觉词汇。
