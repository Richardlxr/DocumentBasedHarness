# Stage: Deck Authoring（大纲之后细化）

先 `comh next --json`：粗大纲尚未接受或委托时按 projection 阶段对齐。
接受后细化页内证据、要点、图表和视觉，用 [deck authoring](../references/deck-authoring.md)
加载具体词汇；只在需要时读主题、素材和动画部分。

草案计划可用顶层 `draft: true`，允许保存和展示大纲，禁止正式渲染；完成内容后移除或设 false。
共同打磨模式每次处理一个页/节，先职责、再要点、后细节；完整页用
`comh present deck_detail --node P01` 展示并记录回复。默认关键节点模式不要求逐页确认。

用户已授权的局部修改直接执行并说明影响；若改变结构，展示新大纲或依据实际用户回复登记当前版本。
保存计划后运行 `comh render deck` 或 `comh render deck-html`；renderer 只读取本地资源。
大纲已对齐、细节尚在打磨时可 `comh render deck-html --preview` 查看草案，或用 deck 输出 PPTX。
预览写入 `.workspace/preview-*`，不产生正式构建凭据，不覆盖 build，不能交付。
