# 图形编译链

## 目标与边界

所有受支持的图形源先归一为原生 `.drawio`：

```text
Mermaid fenced code ─┐
原生 .drawio ────────┴→ mxGraph .drawio → draw.io 26.0.16 CLI → PNG / VSDX
```

对 Markdown 中的 Mermaid 而言，构建生成的 `.drawio` 是可编辑中间格式；对
`drawio-file` 而言，`documents/` 中被引用的 `.drawio` 是规范原始图源。两者都必须包含
独立 vertex/edge `mxCell`，边要有
`source` 和 `target`；禁止 `mermaidData`、`data="mermaid"`、`shape=image` 整图替代。
`build/` 中的 `.drawio`、PNG 和 VSDX 均为可重新生成的构建资产，不应手工修改；DOCX
显示层统一使用高分辨率 PNG。手工维护流程见
[Managed Project 手工维护指南](project-maintenance.md)。

## Markdown 输入

内置 parser 将以下 fenced block 转为 `DiagramBlock`：

- `mermaid`：由注册的 Mermaid 转换器转换；
- `drawio`：内容是完整原生 draw.io XML；
- `drawio-file`：内容是相对 Markdown 文件的 `.drawio` 路径。

普通代码块仍按代码渲染。当前内置 Mermaid 转换器支持 `flowchart`/`graph` 的方向、常用
节点形状、链式连接、实线/虚线/双向边和 `-->|标签|`。它不伪装成完整 Mermaid 实现；
subgraph、class/style/click 等未实现语句会带 Markdown 行号失败。

## CLI 与版本固定

```bash
docx-harness install-drawio
docx-harness convert-diagram source.mmd -o build/source.drawio
docx-harness convert-diagram source.mmd -o build/source.vsdx
docx-harness render report.md -o build/report.docx
docx-harness render report.md -o build/report-visio.docx --diagram-format vsdx
```

自动安装器下载官方 `jgraph/drawio-desktop` 的 26.0.16 Linux x86_64 AppImage，按该版本
`latest-linux.yml` 的 SHA-512 校验后解包到
`$XDG_CACHE_HOME/docx-harness/drawio/26.0.16/`。不支持的平台或受控环境设置
`DRAWIO_CLI=/path/to/drawio`。正常构建不会隐式下载；需要单次命令自动安装时显式传入
`--auto-install-drawio`。

`DrawioCli` 使用官方 `--export --format vsdx|svg|png --output ...`。DOCX renderer
默认请求 3 倍缩放 PNG，以减少页面放大和打印时的锯齿；VSDX 只在显式选择
`--diagram-format vsdx` 时额外生成。独立 `convert-diagram` 仍可按输出后缀生成
`.drawio`/PNG/VSDX/SVG，但 SVG 不属于 DOCX 标准链路。

DOCX 中的显示尺寸由图形自然尺寸和页面边界共同计算。自然尺寸按 Draw.io 的 96 DPI
逻辑坐标和 PNG 导出倍数还原；默认不把小图放大到超过自然尺寸，同时将宽度限制在正文
可用宽度内、高度限制在正文可用高度的 72% 内，为标题、图注和分页保留空间。PNG 与
VSDX 预览共用同一尺寸结果。`DiagramExportProfile` 可通过 `png_scale`、`logical_dpi`、
`max_width_fraction`、`max_height_fraction` 和 `allow_upscale` 调整该策略。

内置 Mermaid 转换器在布局阶段自行计算节点尺寸、显式换行、层间距离和连线避让。
PNG 只是确定性布局的显示快照，不是布局算法或可编辑底稿的替代。

## 确定性布局管线

核心 `DiagramLayoutEngine` 不依赖 draw.io 自动布局。它先用 Pillow 和系统字体匹配得到
实际字形宽度与行高，再按固定规则换行和确定节点尺寸。层级排序后，带标签的相邻层会
按标签实测尺寸扩大间距；同一节点上的扇入/扇出边获得不同边界端口和分层出线通道。

路由器生成直接、L 形、外侧通道和障碍可见图 A* 等多组正交候选，统一对长度、折点、
交叉、共线重叠、近距离平行线、节点、其他标签和已保留端口计分。标签可沿线路移动并
使用显式二维偏移；若已布线路仍有冲突，执行有限次 rip-up/reroute。最后删除不必要的
共线折点，并拒绝以下结果：

相邻层之间还会建立公共对齐通道：完全对齐的节点保持直连；需要转弯时，同一层间的边
优先在同一坐标弯折；跨层边在进入目标层时复用目标层通道。若共用坐标会造成线段重叠，
路由器按 `line_clearance` 移到紧邻的平行通道，形成整齐的线束而不是含义不明的共线。
可用 `DiagramLayoutPolicy.align_rank_channels` 关闭这种吸附，但默认应保留。

- 节点互相重叠；
- 线路穿过无关节点；
- 标签压住节点、其他标签或无关线路；
- 两条边交叉或共享含义不明的线段；
- 缩放到目标 DOCX 内容宽度后，节点字体小于最低可读阈值。

项目可组合 `DiagramLayoutPolicy` 改变最大文字宽度、节点/层间距、净空、候选数、路由
惩罚、目标栏宽和最小字号。布局输入输出是通用数据类，因此新的 DSL 可复用算法而不必
复用 Mermaid parser；若某类图确实允许显式总线或交叉，应在项目策略/转换器中明确建模，
不要靠重叠线段暗示。

## 可复用图形样式

内置转换器默认使用 `SWISS_TECHNICAL_DIAGRAM_STYLE`，公文别名为
`CN_OFFICIAL_DIAGRAM_STYLE`。它借鉴瑞士现代主义信息设计：字体为黑体（draw.io 名称
`SimHei`），统一使用小圆角卡片、细边框和较大留白。配色使用低饱和石板蓝、淡蓝灰、
淡鼠尾草绿和暖灰：控制节点以石板蓝反白形成视觉锚点，普通组件使用冷白卡片，重点
对象使用淡蓝灰和加重边框，外部系统使用淡绿灰虚线卡片，判断节点使用暖灰并保留
菱形。颜色只辅助分组；实线、虚线、边框粗细、箭头和形状仍承担语义，灰度打印时也应
可以辨认。风格不混用传统圆柱、胶囊和双边框造型。

`DiagramStyleProfile` 集中维护字体、字号、填充、边框、标签底色和线宽。公文场景可用
`cn_official_diagram_style(font_family=...)` 在维护的字体集合中选择：`SimHei`、
`FangSong_GB2312`、`KaiTi_GB2312`、`FZXiaoBiaoSong-B05` 或 `NSimSun`。默认使用
`SimHei`；项目若不是公文场景，仍可直接构造通用 profile，不必受公文字体集合限制。

项目需要替换风格时组合 converter，而不是复制整个 Mermaid 实现：

```python
from docx_harness import (
    DiagramConverterRegistry,
    cn_official_diagram_style,
    create_mermaid_flowchart_converter,
)


def create_diagram_registry() -> DiagramConverterRegistry:
    registry = DiagramConverterRegistry()
    style = cn_official_diagram_style(font_family="KaiTi_GB2312")
    registry.add("mermaid", create_mermaid_flowchart_converter(style))
    return registry
```

## DOCX 包装

`DiagramExportProfile(embed_format="png")` 是默认值：PNG 以普通 DrawingML 图片放入
`word/media/`，不依赖查看器的 SVG 或 OLE 绘制能力。显式选择
`embed_format="vsdx"` 时，VSDX 以 `Visio.Drawing.15` OLE relationship 嵌入
`word/embeddings/`，同一 PNG 放入 OLE 的 VML 预览槽。WPS/LibreOffice 可只显示 PNG；
支持该 OLE 对象的 Word/Visio 环境还可打开内嵌 VSDX。

构建目录在 DOCX 旁的 `diagrams/<document-stem>/`，默认保留 `.drawio` 和 PNG；VSDX
模式额外保留 VSDX。同一文档重建时会清理旧哈希命名的图形产物。
图形段落显式使用可随对象高度扩展
的单倍行距，避免继承公文正文的固定行距后裁切 OLE 预览。

不要把 `python-docx.add_picture()` 当作 VSDX 嵌入；VSDX 是包内对象而不是图片。改变
该层时同时检查 DOCX relationship、content type、PNG 尺寸和目标查看器效果。

## 扩展新的源类型

转换器只承担一种职责：把 `DiagramSource` 变为 `DrawioDocument`。项目可以组合注册表：

```python
from docx_harness import DiagramConverterRegistry, default_diagram_registry


def create_diagram_registry() -> DiagramConverterRegistry:
    registry = default_diagram_registry()
    registry.add("my-dsl", convert_my_dsl_to_drawio)
    # 使用 replace=True 可显式替换内置转换器，而无需修改 parser 或 renderer。
    # registry.add("mermaid", project_mermaid_converter, replace=True)
    return registry
```

转换器应显式声明所支持的语法，保留源位置，并为节点、边、禁止插件 payload、CLI 导出
和 DOCX relationship 增加测试。若一个项目只需要特殊布局，可保留在 project 中；只有
转换语义与输出契约稳定且可复用时再提升到核心。
