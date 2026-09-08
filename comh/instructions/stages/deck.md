# Stage: Deck Authoring（大纲之后细化）

先 `comh next --json`：粗大纲尚未接受或委托时按 projection 阶段对齐。
接受后细化页内证据、要点、图表和视觉，用 [deck authoring](../references/deck-authoring.md)
加载具体词汇；只在需要时读主题、素材和动画部分。
使用 context 的 presentation_profile 和 [受众文案规则](../references/audience-copy.md)。
学术场合默认学术充实，用户可改档；“一页一个主旨”不等于“一页只有几个短句”。
先按 [研究与技术汇报](../references/research-presentations.md) 检索架构、实验过程和对照证据，
选择载体、安排连续阅读路径，并默认保持原生可编辑。丰富页面靠条件、证据和解释。参考布局时看分区与阅读顺序，不从参考稿复制空洞标签。
用户指定 PPTX 样式模板时，再读 [样式编译](../references/pptx-style.md)：
只继承背景、品牌元素和文字样式；密度、结构属于另行讨论的风格模板。
若 next 指向 deck_appearance，先完成代表页预览和样式决策，再批量细化。
已有单模板选择不重复问；已接受样式的机械兼容性缺陷直接修复、渲染和检查。

草案计划可用顶层 `draft: true`，允许保存和展示大纲，禁止正式渲染；完成内容后移除或设 false。
共同打磨模式每次处理一个页/节，先职责、再要点、后细节；完整页用
`comh present deck_detail --node P01` 展示并记录回复。默认关键节点模式不要求逐页确认。

用户已授权的局部修改直接执行并说明影响；若改变结构，展示新大纲或依据实际用户回复登记当前版本。
保存计划后运行 `comh render deck` 或 `comh render deck-html`；renderer 只读取本地资源。
大纲已对齐、细节尚在打磨时可 `comh render deck-html --preview` 查看草案，或用 deck 输出 PPTX。
预览写入 `.workspace/preview-*`，不产生正式构建凭据，不覆盖 build，不能交付。
