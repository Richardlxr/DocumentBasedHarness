# 架构

## 稳定边界

1. `parser.py` 使用 MyST/Docutils 解析标准 Markdown 和 directives。
2. `transform.py` 将第三方 AST 规范化为项目自己的不可变 IR。
3. `extension.py` 注册领域 directive、节点转换器和 DOCX renderer。
4. `renderers/docx.py` 只消费 IR，不理解 Markdown 源语法。
5. `table_builder.py` 根据声明式行、单元格和合并跨度创建表格；`table_format.py` 组合
   可替换的视觉与布局 profile；`table_layout.py` 从最终表格网格计算列宽、换行需求和
   行高下限，再由小型 OOXML helper 写入 Word。
6. `diagrams/` 将图形源转换为原生 draw.io 文档，再通过版本固定的桌面 CLI 导出；
   `renderers/diagram_ooxml.py` 只负责把构建产物安全地包装进 DOCX。
7. `math_conversion.py` 验证 TeX，并通过 MathML 适配为 OMML；
   `renderers/math_ooxml.py` 只负责把已校验的 Office Math 节点写入 DOCX。

这使 Markdown 方言、领域模型和 DOCX 细节可以分别演进。

## 数学公式边界

公式遵循 `MyST math 节点 → InlineMath/MathBlock IR → TeX 验证 → MathML → OMML`。
IR 保留原始 TeX 和源位置，renderer 不重新解释 Markdown。第三方转换库隐藏在自有适配层
后面；适配层负责拒绝未解析命令、修复已知且范围明确的兼容问题，并对最终 OMML 做 XML
完整性校验。DOCX 中保存的是可编辑的 Office Math，不使用公式截图，也不把公式当代码块。

独立公式和表格内独立公式分别使用模板样式，字号随正文和表格上下文变化。行内公式直接
进入所在段落，从而继承该段落的排版环境。详见 [数学公式](math.md)。

## 图形编译边界

图形不是普通图片，也不由 DOCX renderer 解析 Mermaid。`DiagramBlock` 仅携带源类型、
内容和位置；`DiagramConverterRegistry` 负责选择转换器；转换器必须返回可验证的
`DrawioDocument`。`DiagramArtifactBuilder` 负责保存 `.drawio` 中间件和调用
`DrawioCli`，`DiagramExportProfile` 决定是否嵌入 VSDX，DOCX 预览统一使用 PNG。

`DiagramStyleProfile` 是独立于布局和导出格式的视觉 token 集合。内置
`CN_OFFICIAL_DIAGRAM_STYLE` 使用黑体和弱饱和、灰度安全的语义配色；项目可组合另一
profile，而不复制 parser、布局或 OOXML 包装代码。

`DiagramLayoutEngine` 是独立于 Mermaid parser 和 draw.io XML writer 的确定性几何层。
它接收语义中立的 `LayoutNodeInput`/`LayoutEdgeInput`，执行：

```text
实际字体度量 → 确定性换行与节点尺寸 → 分层和排序 → 标签感知的层间距
→ 多端口与出线通道分配 → 障碍感知候选路由 → 标签定位与碰撞计分
→ 层间公共通道对齐 → rip-up/reroute → 共线折点简化 → DOCX 栏宽缩放可读性校验
```

布局输出包含节点矩形、边界端口、显式折点、标签相对位置和标签偏移。Mermaid writer
只把这些结果映射为原生 mxGraph cells；项目也可复用该引擎实现另一种源语言，或组合
`DiagramLayoutPolicy` 调整间距、净空、路由代价和最终字号阈值。

默认链路保留 `.drawio` 和高分辨率 PNG，DOCX 作为普通 DrawingML 图片嵌入
PNG。显式选择 VSDX 时，才额外导出并嵌入 Visio 文件，复用同一 PNG
作为 OLE 预览。`.drawio`/VSDX 才是可编辑产物，PNG 只是可移植显示层。详见
`docs/diagrams.md`。

## Core 与 projects

核心包只包含跨文档类别稳定复用的能力。`projects/<name>/` 是拥有独立 Git 的 managed
Project，负责自己的 Markdown、可编辑图源、模板、样式清单、实现和测试。外部仓库只
作为 reference，规范正文必须位于 Project 的 `documents/`。Project runtime 通过
`create_registry()` 组合扩展，并在隔离命名空间中加载本地模块；directive 注册仅在
单次解析作用域内生效，不污染全局注册表。`project.toml` 声明默认 source 和 output，
因此标准 `render-project` 命令不需要项目专属 wrapper 脚本。

Project 子系统按职责拆分为 `config`、`scaffold`、`loader`、`runtime`、`validation` 和
`api`。配置加载只处理版本化输入和路径安全；`validate-project` 另行检查独立 Git 根、
模板、可选样式清单、扩展 runtime 和默认源。Project Python 使用路径与内容摘要组成的
隔离命名空间，同一长进程内修改本地模块后不会继续复用旧实现。完整配置契约见
`docs/projects.md`。

当前边界可按以下问题判断，不设置“使用几个项目才允许提升”的数字门槛：

- 是否不依赖客户、设备、网络场景或单份文档字段；
- 输入输出契约是否能用语义中立的数据结构表达；
- 是否能独立测试，并允许 project 通过 profile/policy 组合而不是复制实现；
- 提升后是否让所有权更清楚，而不是只把文件移到 `src/`。

据此，表格 builder、合并感知列宽/行高、模板 preset、图形样式、字体测量、对齐通道、
避障路由、draw.io 导出、DOCX 包装、语义中立的封面和正文边界属于核心；文档类别的字段
映射、专属 directive、源位置约定和单位细则留在 project。内置 `{document-cover}` 紧随
文档 H1，携带日期语义；默认 renderer 按页面几何将标题水平、垂直居中，将日期置于首页
专用页脚，并以原生分页符结束封面。`{document-body-start}` 只声明后续内容进入正文。项目可
替换具体映射，不需要把空段落数量写进内容源。空的 `extensions.py` 是可选扩展接点，不
表示 project 需要复制核心 renderer。

`init-project --from-docx` 可以生成无正文的基础模板、`style-manifest.json` 和
`components/table-NNN.docx`，为 AI 分析提供现成证据。这些不是强制的长期架构：AI 可
选择性使用、替换或删除，也可以直接视觉分析、检查目标 OOXML 或编写项目专属脚本。
带图片或超链接关系的组件需要显式重建关系，不能盲目复制 XML。

## 模板与 renderer 的分工

模板负责可复用的视觉资产：页面大小、页边距、字体、段落样式、表格样式。renderer
负责结构：创建多少行列、合并哪些单元格、选择布局策略、重复表头，以及将 IR 放入
哪个 Word 元素。

## 表格布局引擎

`table_layout.py` 提供可独立测试的确定性算法。renderer 完成内容和合并后，布局引擎
读取最终表格的 `gridSpan` 与 `vMerge`，因此普通单元格、横向合并和纵向合并使用同一
套计算过程：

- 默认根据各列文本量估算换行成本，并按平方根权重分配父容器可用宽度；跨全表的
  合并标题不参与单列权重计算；也可选择强制等分或通过 `column_weights` 显式调整；
- 横向合并单元格按所跨列宽之和估算换行数；
- 纵向合并单元格的高度需求分摊到所跨各行；
- 中文、拉丁字符、空白和显式换行使用固定的显示宽度模型；
- 行高写为 `atLeast` 下限，算法控制紧凑程度，Word 仍可在字体替换时扩展而不裁字；
- 实际列宽、物理单元格宽度和合并后的宽度均显式写入 OOXML，不使用 Word AutoFit。

项目 renderer 可以构造自己的 `TableLayoutPolicy` 调整字号、行距、内边距、最小列宽
和列权重，不需要复制布局算法。

## 表格 builder 与 profile

`TableSpec`、`TableRowSpec` 和 `TableCellSpec` 只描述列数、行、单元格位置、横纵跨度
以及写入回调。`build_table()` 负责合并范围校验、创建和合并单元格、重复表头、分页
约束、边距、边框及可选布局。回调负责业务内容和语义样式，因此 builder 不理解测试
用例、验收矩阵或其他业务字段。

`TableFormatProfile` 将以下行为独立组合：

- 可选边框 profile；
- 可选单元格边距；
- 可选布局 policy；
- 是否固定布局；
- 是否禁止一行跨页拆分。

`TableRowSpec.prevent_split` 可以逐行覆盖 profile。例如字段行通常保持完整，而包含长篇
正文的合并行可以允许跨页，避免把整张结构化表格推到下一页。

表格测量同时读取普通 `w:t` 和原生公式 `m:t`，因此包含行内 OMML 的字段仍会参与列宽
和行高估算，而不是被当作空内容。

各项均可替换或设为 `None`。`compile_text()`、`compile_file()`、`render_project()` 和
`DocxRenderer` 都接受可选的 `table_profile`；自定义 directive 也可直接给 builder
传入独立 profile。普通 Markdown 表格和内置 `test-case` 使用同一 builder，但项目
仍可绕过它并直接使用 python-docx 或小型 OOXML helper。

`template.py` 是公共模板生成逻辑；managed Project 的 `templates/base.docx` 是受版本
管理的构建输入。正常渲染不得修改模板；Project 使用 `configure_document`、
`finalize_document` 和 `validate_document` hook 修改内存中的输出文档。DOCX 与图形先在
staging 中完整生成和验证，再原子发布到 `build/`。

## 确定性

相同源、模板、依赖版本和输入参数应产生语义一致的 OOXML。ZIP 时间戳等包级元数据
不属于默认保证；若业务要求字节级可重复构建，可在保存后增加规范化重打包步骤。
