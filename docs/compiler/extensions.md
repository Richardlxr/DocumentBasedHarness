# 扩展指南

一个领域扩展由四部分组成：

1. 自定义 Docutils 节点。
2. MyST directive：解析参数和 options，使用 Pydantic 校验。
3. AST → IR 转换函数。
4. IR → DOCX 渲染函数。

`src/docx_harness/directives/test_case.py` 是完整参考实现。新增扩展时创建同类模块，
并在 `default_registry()` 中注册：

```python
registry.add(
    DirectiveExtension(
        name="decision",
        directive=DecisionDirective,
        node_type=DecisionNode,
        ir_type=DecisionBlock,
        transform=transform_decision,
        render=render_decision,
    )
)
```

语法名称应表达内容语义，例如 `decision`、`requirement`、`test-case`。不要使用
`two-column-table`、`red-box` 一类排版名称。

每个扩展至少应测试：有效输入、字段校验失败、IR 结构、DOCX 结构和关键 OOXML 属性。

结构化表格需要已校验的横向或纵向合并以及通用布局时，优先考虑
`TableSpec`、`TableRowSpec`、`TableCellSpec` 和 `build_table()`。通过单元格写入回调
保留本地字段映射；边框、边距、分页或布局策略不同时，从 `TableFormatProfile` 派生。
这些 helper 不是强制框架：如果声明比表格本身更难理解，项目可以直接使用
python-docx 或小型 OOXML helper。

图形源转换使用独立的 `DiagramConverterRegistry`，不要把 Mermaid 语法塞进领域
directive renderer。项目要支持新的图类型时，从 `default_diagram_registry()` 开始组合，
注册一个 `DiagramSource → DrawioDocument` 转换器，并可在 `extensions.py` 暴露
`create_diagram_registry()`。转换结果必须是原生 mxGraph 节点和边；不支持的源语法应
带位置报错，禁止回退为 Mermaid 插件对象或整体图片。参见 [图形编译链](diagrams.md)。
