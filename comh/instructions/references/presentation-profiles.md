# 内容密度与布局建议

此配置决定信息展开程度，不决定背景、字体或品牌资源。样式模板仍由 appearance 管理。
参考布局不意味着照搬原文、内容槽位或坐标，不把密度/页码写入 narrative。

## 选择与默认

有演示稿输出时，在 Gate 1 记录 `brief.presentation` 并纳入 alignment。
根据已知场合记录 setting，不靠“学术腔”的词汇推断读者需要多少信息：

```yaml
presentation:
  setting: academic
  # 未指定 profile 时，academic 自动采用 academic-rich；general 采用 balanced。
```

学术汇报、组会、技术研究评审默认采用**学术充实**，除非用户明确要求别的密度。
用户已说“简短”“多展开一些”或给了参考时直接记录；否则把默认建议放进契约一起确认，
不额外强迫用户挑档。非学术场合也能主动选择学术充实。它独立于 plain/formal 等语言语域。

| profile | 内容取向 | 中文正文页可见文字参考 | 常见主体分区 |
|---|---|---|---|
| academic-rich | 条件、证据、解释、结论充分展开 | 约 300–550 字符 | 2–4 块 |
| balanced | 关键证据与必要解释 | 约 160–320 字符 | 2–3 块 |
| concise | 一个结论和最有力证据 | 约 60–180 字符 | 1–2 块 |

这些是**检查信号，不是字数配额或信息质量分数**。中文字符计数包含拉丁字母/数字，
去除空白；已结构化的图标签和表格文案计入，图片内部文字不计。英文采用独立词数范围。主图页可以少字，封面/分节/结尾不套正文阈值。
字数不足时先问“缺了哪项必要解释/证据”，不是加废话；充足证据不存在时保留缺口，不能补造。
不通过缩小字号达成密度，也不为了满足档位引入第二个无关主题。

用户可用自然语言调整，也可直接配置：

```yaml
presentation:
  setting: academic
  profile: balanced
  overrides:
    text_budget: {zh_chars: [200, 400]}
    substantive_blocks: [2, 3]
    layout_patterns:
      - 主图配两组解释，结论与限制放在一起
```

`comh presentation-profiles [academic-rich|balanced|concise]` 可独立查询。
`comh context --stage deck` 提供当前生效配置；只在投影/演示稿细化阶段加载完整指南。
`spec.dimensions` 仍是开放偏好，代码不解释；如其中含用户明确密度要求，agent 在 Gate 1
将其落实为 presentation 配置并保持一致，不让默认值覆盖用户要求。

## 学术充实的内容与布局

- **问题总览**：简短引入 + 并列问题。每块说明要检验什么，不用“甲方关心的价值”等内部标签。
- **结果页**：主图/已有对照材料占主体，解释紧邻其对应证据，底部放结论和成立条件。
- **机制/方法页**：步骤或分区有明确阅读顺序，参数、对照与方法说明服务于同一问题。
- **总结页**：逐项回答先前问题，再给适用条件与下一步；不要把所有标题重复一遍充数。

参考布局取其分组、层级、图文邻接与阅读顺序，不复制背景、配色和边框。按内容选择当前
renderer 支持的 page_role、support_points 的 point/detail、chart/diagram/asset_refs 与 callout。
现支持 `visual.table` 原生表格和 `visual.arrangement: full|split|columns` 的受约束布局；
具体接口见 deck-authoring，阅读路径检查见 [研究与技术汇报](research-presentations.md)。
这不是任意网格；超出引擎能力时要说明，不能写一个不会渲染的字段。
布局建议可以调整；共同打磨时继续逐页对齐，不新增一套独立的强制密度审批流程。

同时执行 [受众文案规则](audience-copy.md)：信息充实应来自有用内容，而不是概念标签、
省略动词的名词串或对整页的抽象评价。
