# Changelog

All notable changes to the ViMax project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added - 2025-11-06

#### Idea2Video 场景规划集成 (Scene Planning Integration for Idea2Video)

**新增功能**：

1. **Idea2Video Pipeline 场景规划集成** (`pipelines/idea2video_pipeline.py`) 🆕

   - 添加 `ScenePlanner` 初始化
   - 新增 `plan_scenes()` 方法：在编写剧本后统一规划场景
   - 更新 `extract_characters()` 方法：接收并传递场景定义
   - 重构主流程 `__call__()`：
     - 在 `write_script_based_on_story()` 之后调用 `plan_scenes()`
     - 将完整剧本传递给 ScenePlanner 进行场景分析
     - 添加场景数量验证（ScenePlanner vs Screenwriter）
     - 将统一的场景定义传递给 CharacterExtractor
     - 为每个场景调用 Script2Video 时传递对应的场景定义

2. **Script2Video Pipeline 场景参数优化** (`pipelines/script2video_pipeline.py`)

   - `__call__()` 方法新增 `scenes` 参数
   - 优先使用上游传入的场景定义（来自 Idea2Video）
   - 避免重复调用 ScenePlanner（节省计算资源）
   - 如果没有传入场景，保持原有逻辑（从文件加载或重新生成）
   - 自动将传入的场景保存到 `scenes.json` 以便缓存

3. **SceneDefinition 接口导出** (`interfaces/__init__.py`)
   - 在 `__init__.py` 中添加 `SceneDefinition` 导出
   - 确保所有 pipeline 都能正确导入场景定义类型

**效果**：

- ✅ Idea2Video 和 Script2Video 使用完全统一的场景定义
- ✅ 从 Idea 到最终视频，scene_id 在全流程中保持一致
- ✅ 避免重复生成场景，提升计算效率
- ✅ 角色外观正确映射到每个场景
- ✅ 场景环境一致性进一步增强

#### 统一场景规划系统 (Scene Planning System)

**背景问题**：

- CharacterExtractor 和 StoryboardArtist 独立定义场景，导致 scene_id 不一致
- 角色外观的 scene_ids 与镜头的 scene_id 可能不匹配
- 无法保证同一场景内生成帧的环境一致性

**新增功能**：

1. **ScenePlanner Agent** (`agents/scene_planner.py`) 🆕

   - 实现 `plan_scenes()` 方法：分析剧本，识别场景边界，生成统一的场景定义
   - 输出场景定义列表（SceneDefinition），包含：scene_id、location、time_of_day、description、script_excerpt
   - 场景 ID 从 0 开始递增，确保全局唯一性
   - 生成 `scenes.json` 供后续 Agent 使用

2. **SceneDefinition 接口** (`interfaces/scene.py`) 🆕

   - 定义场景数据结构：scene_id、location、time_of_day、description、script_excerpt
   - 使用 TYPE_CHECKING 避免循环依赖

3. **CharacterExtractor 场景集成** (`agents/character_extractor.py`)

   - `extract_characters()` 方法新增 `scenes` 参数
   - 接收 ScenePlanner 提供的场景定义
   - 在提示词中提供场景信息，指导 LLM 使用统一的 scene_id
   - 确保角色外观的 scene_ids 与场景定义一致

4. **StoryboardArtist 场景集成** (`agents/storyboard_artist.py`)

   - `design_storyboard()` 方法新增 `scenes` 参数
   - 接收 ScenePlanner 提供的场景定义
   - 在提示词中提供场景信息，要求为每个镜头分配对应的 scene_id
   - 从"独立识别场景"改为"使用预定义场景"

5. **ReferenceImageSelector 场景上下文增强** (`agents/reference_image_selector.py`)

   - `select_reference_images_and_generate_prompt()` 新增 `scene_definition` 参数
   - 构建场景上下文字符串（location、time_of_day、description）
   - 在所有提示词生成路径（预过滤、多模态选择、降级、提示词生成）注入场景上下文
   - 增强场景环境一致性：指导 LLM 选择符合场景环境的参考图并生成一致的描述

6. **Pipeline 场景规划流程** (`pipelines/script2video_pipeline.py`)

   - 在 `__call__()` 方法最开始添加场景规划步骤
   - 调用 `ScenePlanner.plan_scenes()` 生成场景定义列表
   - 将场景定义保存到 `self.scenes_dict` 供后续使用
   - 在调用 `CharacterExtractor.extract_characters()` 时传入 scenes
   - 在调用 `StoryboardArtist.design_storyboard()` 时传入 scenes
   - 在 `generate_frame_for_single_shot()` 中根据 scene_id 查找对应的 SceneDefinition
   - 在调用 `ReferenceImageSelector.select_reference_images_and_generate_prompt()` 时传入 scene_definition

7. **文档完善**
   - 新增 `docs/SCENE_PLANNING_IMPLEMENTATION.md`：详细说明场景规划系统的实现
   - 新增 `docs/SCENE_CONSISTENCY_ENHANCEMENT.md`：记录场景一致性增强方案
   - 更新 `docs/AGENT_LOGIC_ANALYSIS.md`：
     - 新增 ScenePlanner 章节（第 2 节）
     - 更新 CharacterExtractor、StoryboardArtist、ReferenceImageSelector 章节
     - 更新 Pipeline 流程图（8 步流程）
     - 更新多外观工作流程，展示统一场景规划
     - 更新场景管理机制、优化优先级表、系统优化章节
     - 版本号更新为 v1.1
   - 更新 `docs/TODO.md`：添加场景参考图生成长期方案（P1 优先级）

**关键改进**：

- ✅ scene_id 在所有 Agent 间完全一致（来自同一个 ScenePlanner）
- ✅ 角色外观 scene_ids 与镜头 scene_id 完美匹配
- ✅ 场景上下文增强了环境一致性（短期方案）
- 📋 场景参考图生成（长期方案，已规划）

**架构优势**：

- 采用"预规划"模式：先定义场景，再让所有下游 Agent 使用
- 单一数据源（ScenePlanner）确保一致性
- 场景定义可序列化（scenes.json），便于调试和复用
- 向后兼容：未提供 scenes 参数时仍可正常工作

#### 一致性优化系统 (Consistency Optimization System) - v1.2 🆕

**背景问题**：

基于 `docs/history_enhance/CONSISTENCY_ISSUES_ANALYSIS.md` 的问题分析，发现并发生成带来的一致性问题：

- 场景内环境元素（道具、家具、布局）不连贯
- 后续镜头先完成导致缺少环境参考
- 选图时过度关注角色，忽略环境一致性
- 镜头缺少 scene_id 导致过滤失效
- 视频生成失败导致整个流程中断

**新增功能**：

1. **P1 优化: 场景环境参考帧动态收集** (`pipelines/script2video_pipeline.py`) 🆕

   - 实现 `collect_completed_frames_for_scene()` 方法
   - 动态收集同场景已完成的帧作为环境参考（最多 5 个）
   - 在生成每一帧前，自动添加同场景的环境参考
   - 日志标记：`✨ P1优化: 添加了 N 个已完成的帧作为环境参考`

2. **P2 优化: 相机时序控制** (`pipelines/script2video_pipeline.py`) 🆕

   - 识别优先级镜头（priority_shot_idxs）
   - 确保第一个镜头的末帧优先完成
   - 使用 asyncio.Event() 等待末帧完成
   - 日志标记：`✨ P2优化: 镜头 X 是优先级镜头，确保末帧优先完成`

3. **P3 优化: 场景定义验证** (`pipelines/script2video_pipeline.py`) 🆕

   - 在生成帧前验证 scene_id 是否存在于 scenes_dict
   - 及早发现配置问题，提供清晰的警告日志
   - 日志标记：`⚠️ P3警告: 镜头 X 没有关联的场景ID`

4. **P4 优化: 视频生成容错机制** (`pipelines/script2video_pipeline.py`) 🆕

   - 添加 10 分钟超时控制（asyncio.wait_for）
   - 文件存在性验证
   - 详细的错误日志记录
   - 避免无限等待和静默失败

5. **P5 优化: BestImageSelector 环境权重优化** (`agents/best_image_selector.py`) 🆕

   - 重新调整评估权重：
     - 环境一致性：40%（最高优先级）
     - 角色一致性：30%
     - 描述准确性：20%
     - 空间一致性：10%
   - 更新系统提示词，强调环境一致性的重要性

6. **文档完善**
   - 新增 `docs/history_enhance/CONSISTENCY_ISSUES_ANALYSIS.md`：详细分析一致性问题
   - 新增 `IMPLEMENTATION_SUMMARY.md`：记录所有优化实现细节
   - 更新 `docs/AGENT_LOGIC_ANALYSIS.md`：
     - 新增"一致性优化系统 (v1.2)"章节（第 10 节）
     - 更新 ReferenceImageSelector、BestImageSelector、Pipeline 章节
     - 添加 P1-P5 优化标记和代码示例
     - 更新优化优先级表和总结部分
   - 更新 `docs/TODO.md`：标记 P1-P5 优化已完成

**关键改进**：

- ✅ 场景环境一致性显著提升（P1 + P5）
- ✅ 生成顺序更合理（P2）
- ✅ 系统鲁棒性增强（P3 + P4）
- ✅ 道具位置、光线、色调更连贯

**测试验证**：

- 创建完整测试脚本 `test_consistency_optimization.py`
- 实现 MockVideoGenerator 和 MockCameraImageGenerator
- 添加断点续传功能（checkpoint/resume）
- 验证 P1-P5 优化的日志输出

---

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
