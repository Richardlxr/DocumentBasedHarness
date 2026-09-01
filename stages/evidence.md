# Stage: Evidence（事实提取）

## 输入

- `sources/` 下的全部材料（CSV / XLSX / 日志 / PDF / Markdown / 图片 / 已有文档）。
- 用户对材料的口头说明（如有）。

## 你做什么

把材料里**将来可能被引用的事实**逐条提取为 evidence 条目，写入 `evidence/evidence.yaml`。
你不是在总结材料，而是在建立一个**可引用的事实库**：后面所有 claim、每一页 slide、
报告里的每个数字，都只能引用这里的条目。

条目规则：

- `id`：`E001` 起顺序编号，全局唯一，永不复用。
- `kind`：开放词汇。内置语义：`datum`（数据点）/ `quote`（原文引用）/ `table` /
  `figure` / `fact`（非数值事实）/ `assumption`（假设）。可以发明新 kind。
- `content`：一句话说清这个事实是什么，人类可读。
- `source`：`source` 填 `SRCxx`（在文件头 `sources:` 里登记每个源文件），
  `locator` 精确到可复查的位置：`sheet=latency,row=12`、`p.4 第2段`、`行 57-63`。
  有原文时附 `quote`。
- **数字类条目必须带 `value: {number, unit, label}`**——这是数字一致性校验的锚点。
- `observed_at`（可选）：该观测/测量的时间（ISO 日期）。数据时效是溯源的一部分：
  将来 QA 用它检查"结论引用的是不是最新观测"。
- 图片/表格资产提取到 `assets/`，条目里用 `asset:` 引用路径。

## 派生数字规则（重要）

任何不在源材料里、需要计算得出的数字（降幅、均值、差值、百分比），必须先落成一个
evidence 条目再使用：`kind: datum`，`source.locator` 写 `derived:(E001,E002)`，并带
`value`。**没有落库的派生数字出现在 claim 或成品里，会被校验器判为 finding。**

## 提取纪律

- 不确定的不提取；存疑但重要的，提为 `fact` 并在 `note:` 里写明不确定性。
- 材料之间互相矛盾的，两条都提，各自标注来源，交给 narrative 阶段处理。
- 宁可多提背景事实，不要提前下结论——结论属于 narrative 的 claim，不属于这里。

## 收尾

```
comh save evidence
```

保存即记录上游 `sources/` 的指纹；之后材料任何增删改都会把 evidence 标脏。
