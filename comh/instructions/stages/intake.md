# Stage: Intake（轻量了解）

先确定调查方向，再展开材料。已有用户信息直接提取，缺失且会改变目标的信息才问。
能从材料查清的事实由你查，不要求用户重复说明。此时不提前承诺结论。

记录目标草案、材料范围与依据到 `.workspace/intake.yaml`：

```yaml
goal: 这次沟通希望帮助受众做什么决定
source_scope: 优先检查哪些材料，哪些只作背景
basis: 用户原话或消息引用
open_questions: []
```

执行 `comh intake .workspace/intake.yaml`，然后 `comh next --json`。
未回答的 intake 问题仍需在 brief 中回答或明确延期，不能因为换阶段而遗忘。

默认协作方式为关键节点对齐。用户要求一起打磨或委托细化时，执行
`comh collaborate collaborative|delegated --reply '用户原话' --source '消息引用'`。
不用重复确认已给出的选择。“不用逐页磨”不等于已经确认故事线。

当前所需的材料先建立清单，再逐步提取；覆盖范围如实写入 coverage，未读不能报为读完。
