# Stage: Brief（沟通契约）— Gate 1

## 输入

- `evidence/evidence.yaml`（事实库概况：材料里有什么、没什么）。
- 用户的自然语言描述：给谁看、想干什么、有什么要求。

## 你做什么

**推断，而不是审问。** 把用户的话 + 材料概况合成为一份沟通契约，写入
`brief/brief.yaml`，然后把要点摘成一页人类可读的摘要给用户确认。

字段纪律：

- `language`：所有交付物（deck、报告）的语言（如 `zh-CN`、`en`）。显式确认，不许下游
  猜——renderer 选字体、模板选择、各 stage 的写作语言都消费它。
- `audience`：具体的人，不是标签。"客户方技术负责人，熟悉存储系统但不了解我们的
  缓存方案" 远好于 "technical"。
- `objective`：这次沟通要达成什么决定/行动/认知。
- `delivery_context`：场合与时长（"30 分钟客户评审会" / "异步阅读的周报"）。
- `media`：每个输出 `{medium, surface}` 二元组。当前支持 `pptx/presentation`、
  `markdown/report`（docx 为编译副产物）、`html/*`（预留）。
- `takeaways`：受众看完应该记住什么。**这是 QA 读者测试的比对基准**，写具体。
- `constraints.hard`：只有能落到确定性检查的才放这里（如 "不要黑底" → renderer
  白名单；"必须包含:局限性" → report 存在性检查）。无法落到检查点的，向用户提议
  降级为 soft preference，并说明原因。
- `constraints.soft`：偏好，尽力满足不保证。
- `visual_materials`（素材方向，Gate 1 必谈）：这批成品的视觉素材从哪来——
  纯排版（typography-only 也是显式选择）/ 图标点缀（`assets/vendor/tabler-outline`，
  5 千+语义图标）/ 需要配图（用户提供 or 显式申请外部获取，绝不静默抓取）。
  写成开放字段记进 brief，deck 投影时消费。
- `spec.dimensions`：自由发明的维度表（`technical_rigor`、`storytelling`、
  `evidence_density`、以及任何你觉得能表达这次沟通风格的新词）。代码只透传不解释，
  下游靠你自己在各 stage 里贯彻。
- `open_questions`：你问过用户的问题和回答原样记录——对齐过程本身要可审计。

## 优先级（下游所有 stage 遵守）

```
用户硬约束 > 用户明确偏好 > 已确认的 spec > 你的推断 > preset 默认
```

## Gate 1（硬规则）

给用户看：语言 / 受众 / 目标 / 场合 / 媒介 / 期望带走什么 / 硬约束清单 / spec 摘要。
用户修改后你更新文件，用户确认后执行：

```
comh save brief
comh confirm brief      # 必须由用户明确同意后才能执行
```

未过 Gate 1 时，narrative 及之后所有 stage 的 save 都会被 CLI 拒绝——不要试图绕过。
brief 在 Gate 之后修改会自动作废确认，需要用户重新确认，这是刻意设计的代价可见。
