# Changelog

All notable changes to the ViMax project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added - 2025-11-05

#### 风格一致性控制系统

**背景问题**：
- 图像生成过程中出现风格突变（动漫风格变真人风格）
- AI 模型生成的 `text_prompt` 有时为 `None`，导致参考图未被正确使用
- 缺少全局风格控制机制

**新增功能**：

1. **ReferenceImageSelector 增强** (`agents/reference_image_selector.py`)
   - 新增 `generate_prompt_for_selected_images()` 方法：当 AI 模型未生成 prompt 时，单独调用 AI 生成高质量 prompt
   - 为 `select_reference_images_and_generate_prompt()` 添加 `style` 参数支持
   - 增强 `_validate_prompt_mapping()` 方法：
     - 检测 `text_prompt` 为 `None` 或空时自动触发补救机制
     - 调用 AI 重新生成包含风格信息的 prompt
     - 添加 `style` 参数支持，确保生成的 prompt 包含风格指示

2. **Pipeline 风格控制** (`pipelines/script2video_pipeline.py`)
   - `Script2VideoPipeline.__init__()` 添加 `style` 参数存储
   - `__call__()` 方法保存 `self.style` 供全流程使用
   - 在调用 `select_reference_images_and_generate_prompt()` 时传入 `style` 参数（两处）
   - 添加防御性检查：当 `text_prompt` 为 `None` 时使用帧描述并附加风格信息

3. **调试日志增强**
   - 在参考图选择后输出详细信息（选择的图片索引、生成的 prompt、参考图描述）
   - 在图像生成前输出最终 prompt 和使用的参考图数量
   - 使用醒目的分隔线和 emoji 提高日志可读性
   - 区分正常流程和降级流程（text-only fallback）的日志输出

4. **文档完善**
   - 新增 `docs/STYLE_CONSISTENCY_WORKFLOW.md`：详细说明风格一致性控制的完整工作流程
     - 问题背景和核心问题分析
     - 完整的工作流程图解（从初始化到每一帧生成）
     - 关键组件详解（ReferenceImageSelector、Pipeline）
     - 五层风格控制防护机制
     - 问题诊断与修复指南
     - 调试技巧和最佳实践

### Changed - 2025-11-05

#### ReferenceImageSelector 接口变更

**Breaking Changes**：
- `select_reference_images_and_generate_prompt()` 新增可选参数 `style: str = None`
- `_validate_prompt_mapping()` 签名变更：
  - 从同步方法改为异步方法（`async def`）
  - 新增 `style: str = None` 参数

**影响范围**：
- 所有调用 `select_reference_images_and_generate_prompt()` 的地方需要传入 `style` 参数
- 所有调用 `_validate_prompt_mapping()` 的地方需要使用 `await`

#### 日志输出改进

**变更内容**：
- 将关键信息从 `logging.info()` 改为 `print()` 输出，确保在终端可见
- 预筛选日志从 "Filtered image idx" 改为更清晰的格式
- 添加多语言 emoji 标识提高可读性

### Fixed - 2025-11-05

#### Bug 修复

1. **修复 `text_prompt` 为 `None` 导致的风格丢失问题**
   - **问题描述**：当 AI 模型返回 `{"ref_image_indices": [0,1], "text_prompt": null}` 时，pipeline 拼接 prompt 会变成 `"Image 0: ...\nNone"`，导致图像生成器收到无效指令
   - **根本原因**：
     - AI 模型能正确选择参考图，但未能生成对应的 text_prompt
     - Pydantic 解析器未严格拦截 `null` 值
     - Pipeline 直接使用 `None` 进行字符串拼接
   - **解决方案**：
     - 在 `_validate_prompt_mapping()` 中检测 `None` 或空字符串
     - 触发补救机制，调用 `generate_prompt_for_selected_images()` 让 AI 专门生成 prompt
     - 在 Pipeline 中添加二次检查，确保 prompt 有效

2. **修复风格信息未传递到场景生成的问题**
   - **问题描述**：虽然 `style` 参数传入了 pipeline，但在生成场景图片时未使用，只在生成角色肖像时使用
   - **解决方案**：
     - 在 `Script2VideoPipeline` 中保存 `self.style`
     - 在所有调用 `ReferenceImageSelector` 的地方传入 `style` 参数
     - 在补救机制中强制包含 `style` 信息

3. **修复区域限制导致的 API 失败问题**
   - **问题描述**：尝试使用 Google Gemini 多模态 API 时出现 `403 PERMISSION_DENIED - Region not supported` 错误
   - **现有机制**：代码已有降级处理，自动切换到纯文本模式
   - **改进**：添加更清晰的错误日志，说明降级原因

### Technical Details - 2025-11-05

#### 新增方法详解

**`ReferenceImageSelector.generate_prompt_for_selected_images()`**
```python
async def generate_prompt_for_selected_images(
    self,
    selected_image_descriptions: List[str],
    frame_description: str,
    style: str = None,
) -> str
```

**功能**：
- 专门用于生成 text_prompt 的补救方法
- 不重新选择图片（图片已经选好）
- 强制 AI 在 prompt 中包含风格信息
- 通过明确的 system prompt 指示 AI 必须包含 `"Image N"` 引用

**调用时机**：
- 当主流程的 AI 模型返回 `text_prompt: null` 时
- 由 `_validate_prompt_mapping()` 自动触发

#### 风格控制五层防护

```
Layer 5: Pipeline 最终检查
         检查 prompt 是否为 None，附加 style
         ↑
Layer 4: 补救机制
         generate_prompt_for_selected_images() 重新生成（含 style）
         ↑
Layer 3: Prompt 验证
         _validate_prompt_mapping() 检测并触发补救
         ↑
Layer 2: 参考图选择
         select_reference_images_and_generate_prompt() 传入 style
         ↑
Layer 1: 源头控制
         用户指定 style，Pipeline 保存并传递
```

#### 代码改动统计

**修改的文件**：
- `agents/reference_image_selector.py` - 主要改动
  - 新增 1 个方法（60+ 行）
  - 修改 3 个方法签名
  - 增强验证逻辑（30+ 行）
  - 添加详细日志输出（20+ 行）

- `pipelines/script2video_pipeline.py` - 接口适配
  - 修改 `__init__()` 添加 style 参数
  - 修改 `__call__()` 保存 style
  - 修改 2 处方法调用传入 style
  - 添加防御性检查（10+ 行）
  - 添加调试日志输出（15+ 行）

- `docs/STYLE_CONSISTENCY_WORKFLOW.md` - 新增文档（500+ 行）

**新增的诊断脚本**：
- `debug_text_prompt_issue.py` - 用于分析 `text_prompt` 为 `None` 的问题

### Migration Guide - 2025-11-05

#### 对于调用 ReferenceImageSelector 的代码

**之前**：
```python
output = await selector.select_reference_images_and_generate_prompt(
    available_image_path_and_text_pairs=images,
    frame_description=desc,
)
```

**现在**：
```python
output = await selector.select_reference_images_and_generate_prompt(
    available_image_path_and_text_pairs=images,
    frame_description=desc,
    style="Realistic Anime, Detective Conan Style",  # 新增参数
)
```

#### 对于自定义 Pipeline

如果你实现了自己的 Pipeline，需要：

1. 在初始化时保存 `style` 参数
2. 在调用图像生成相关方法时传入 `style`
3. 在最终生成 prompt 时确保包含 `style` 信息

### Performance Impact - 2025-11-05

**API 调用次数**：
- 正常情况：无变化（主流程成功时不触发补救）
- 异常情况：+1 次 API 调用（仅在 `text_prompt` 为 `None` 时触发补救）
- 预计触发率：< 10%（取决于使用的 AI 模型质量）

**优化建议**：
- 如果频繁触发补救机制，考虑：
  - 优化主流程的 system prompt
  - 使用更强大的 AI 模型（如 GPT-4 而非 lite 版本）
  - 调整 temperature 参数提高输出稳定性

### Known Issues - 2025-11-05

1. **Pydantic 验证不够严格**
   - 当前 `text_prompt: str` 字段仍可能接收 `None` 值
   - 建议后续版本升级为 `text_prompt: str = Field(..., min_length=1)` 强制非空

2. **Style 信息可能被 AI 模型忽略**
   - 即使 prompt 中包含 style，某些图像生成模型仍可能不遵循
   - 建议使用支持 style reference 的模型（如 Stable Diffusion with ControlNet）

3. **多模态 API 区域限制**
   - Google Gemini Vision API 在某些区域不可用
   - 当前通过降级到纯文本模式解决，但可能影响参考图选择质量

### References - 2025-11-05

**相关文档**：
- [风格一致性工作流程](docs/STYLE_CONSISTENCY_WORKFLOW.md) - 详细的技术文档
- [架构文档](docs/ARCHITECTURE_ZH.md) - 系统整体架构

**相关 Issue**：
- 风格突变问题：动漫风格变真人风格
- `text_prompt` 为 `None` 问题分析
- 区域 API 限制的降级处理

---

## [Previous Versions]

<!-- 之前的版本记录将在这里添加 -->
