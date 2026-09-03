# Stage: Projection（先对齐大纲）

输入是已确认的 brief 与 narrative。先 `comh next --json`；故事线仍在等待回复时停止投影。

按所选媒介起草 deck_plan/report_plan：只先确定页或节的职责、顺序、标题、beat 覆盖与取舍。
大纲由这些字段生成，不额外维护一份 outline.md。报告和演示稿可以有不同展开顺序。
草案仍需满足 schema 和引用规则；暂缺的内容不可冒充已完成的正文。

保存对应计划，执行 `comh present deck_outline` 或 `comh present report_outline`。
用人类可读的结构给用户看，附重要取舍，等待回复。按 [对话协议](../references/dialogue-protocol.md)
记录接受、修改或委托；present 的输出只代表待确认，不能自行填回复。

- checkpoints：粗大纲接受后自主细化。
- collaborative：先对齐粗大纲，再每次处理一个页/节，按“职责与顺序 → 要点和证据 → 细节”推进；
  当前页/节完整后 `comh present deck_detail --node P01` 或 `report_detail --node R01`，记录用户回复。
  所有所选页/节完成对齐或明确委托后，才能正式渲染或保存报告正文。
- delegated：仍展示粗大纲，用户可以回复明确委托；记录 delegated，不能伪装成已审阅具体内容。

用户可随时调整协作档位。拒绝的方向、当前请求及回复留在 run.yaml，恢复后先读取。
修改大纲结构会使其确认失效；只改变主题、字体等样式不会改变粗大纲的结构指纹。

到具体 authoring 再读 [deck](deck.md) 或 [report](report.md)，不提前加载全部视觉词汇。
