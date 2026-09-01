# 模板 presets

模板 preset 是由 Python 维护的可选起点。查看现有 preset：

```bash
docx-harness list-presets
```

生成独立模板：

```bash
docx-harness init-template templates/standard.docx --preset standard
docx-harness init-template templates/cn-official.docx --preset cn-official
```

初始化使用指定 preset 的文档类别：

```bash
docx-harness init-project official-notices \
  --workspace projects \
  --preset cn-official
```

## standard

中性的 A4 技术文档模板，适合一般报告、说明和项目文档。

## cn-official

参考现行 [GB/T 9704—2012《党政机关公文格式》](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=F3CC9BEF482524C895FDA7A08BB4A70E)
中适合直接映射到 DOCX 的通用规定：

- A4 纸张，210 mm × 297 mm；
- 天头 37 mm、订口 28 mm，版心约 156 mm × 225 mm；
- 国家标准中的一般正文通常使用 3 号仿宋体，每段左空二字；
- 一般每面 22 行、每行 28 字；
- 公文标题使用 2 号小标宋体；
- 第一、第二层结构层次分别使用黑体和楷体，后续层次使用仿宋体；
- 页码使用 4 号半角宋体数字和一字线，奇偶页分别靠切口一侧。

当前仓库根据实际文档约定，将“正文”和“正文文本”拆为两个样式：“正文”使用
14 pt 近似四号字且不缩进，“正文文本”继承“正文”并增加两字首行缩进。标题使用
22 pt 近似二号字，正文仍用约 28.95 pt 固定行距逼近 225 mm 版心中的 22 行。

表格统一采用无底色的素表：表头、用例题头和内容均使用黑色文字，表格文字使用
12 pt 近似小四号字；外边框为 1.5 磅，内部横线和竖线为 0.5 磅。需要彩色表格的项目
应在自己的模板或扩展中显式实现，不由通用 renderer 硬编码。

表格内部按语义区分样式：普通 Markdown 表格的首行使用“表格题头”并默认居中；
测试用例的合并名称行使用“测试用例题头”并默认居中；“用例 ID”“优先级”等键名
使用独立的“表格字段标签”并保持左对齐，表格内容仍使用“表格文本”。

通用表格使用确定性的紧凑布局：占满当前正文或父单元格的可用宽度，各列默认按内容
密度分配宽度，短字段列收窄、长内容列扩宽；单元格允许自动换行，行高由布局引擎
根据内容、字号、列宽和合并跨度计算，并以
`atLeast` 下限写入；单元格上下边距为 2 pt、左右边距为 3 pt。
这既适用于两列、四列表格，也适用于更多列，避免依赖不同 Word 实现结果不一致的
AutoFit 算法。需要严格平分时可选择 `equal` 策略；业务表也可提供显式列权重。

这是参考 preset，不是对任一具体机关、文种或办公环境的合规认证。它没有硬编码：

- 发文机关名称、文号和签发人；
- 版头内容及具体红头尺寸；
- 印章、版记和抄送机关；
- 联合行文、信函、命令和纪要等专门版式；
- 某一单位的字体替代、套红、打印和装订细则。

这些内容应由对应 project 的 AI 根据真实样稿、文种和单位规则，选择样式、directive
或专用 renderer 实现。机器缺少方正小标宋、仿宋_GB2312、楷体_GB2312 等字体时，
Word 或 LibreOffice 会替换字体，分页和换行可能变化，应在目标环境验证。

除国家标准信息页外，参数实现时还交叉参考了公开的标准正文展示：
[中国矿业大学（北京）党政办公室](https://dzb.cumtb.edu.cn/info/1040/1184.htm)。
