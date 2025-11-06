# 场景一致性增强 - 实施记录

## 背景

在实施了统一场景划分（ScenePlanner）之后，发现了新的问题：

**问题**：虽然人物外观一致性通过 `scene_id` 过滤得到了保证，但**场景环境一致性**主要依赖于：

1. 分镜描述（StoryboardArtist 生成）
2. 前一帧图像作为参考
3. LLM 的"理解能力"

这些都是"软约束"，不能保证同一场景的不同镜头具有一致的背景环境。

**具体问题场景**：

```
场景0：办公室内部 - 早晨
镜头0：全景，展示办公室环境
镜头1：Alice特写
镜头2：Bob特写
镜头3：双人中景

场景1：同一办公室 - 下午
镜头4：全景，展示办公室环境
镜头5：Alice特写
```

镜头 0 和镜头 4 都是"办公室全景"，但因为是不同镜头，可能生成**完全不同的办公室布局**（桌子位置、窗户、装饰品等）。

## 解决方案

### 短期方案（已实施）：增强 ReferenceImageSelector 的场景感知

在 `ReferenceImageSelector.select_reference_images_and_generate_prompt()` 中：

1. **新增参数 `scene_definition: SceneDefinition`**

   - 传入完整的场景定义（location, time_of_day, description）

2. **在提示词中加入场景上下文**

   ```
   **SCENE CONTEXT (CRITICAL FOR CONSISTENCY):**
   - Location: {scene.location}
   - Time of Day: {scene.time_of_day}
   - Scene Description: {scene.description}

   **IMPORTANT**: The generated image MUST maintain environmental consistency
   with this scene context. The background, lighting, atmosphere, and overall
   setting should match the location and time specified above.
   ```

3. **在所有调用点加入场景上下文**
   - text-only 模式
   - multimodal 模式
   - fallback 模式

### 实施细节

#### 1. 修改 `agents/reference_image_selector.py`

- 导入 `SceneDefinition`
- 方法签名增加 `scene_definition` 参数
- 构建 `scene_context` 字符串
- 在所有 prompt 中附加 `scene_context`

#### 2. 修改 `pipelines/script2video_pipeline.py`

- 在 `__call__` 中保存 `self.scenes` 和 `self.scenes_dict`
- 在 `generate_frame_for_single_shot` 中：

  ```python
  # 获取场景定义
  scene_definition = None
  if scene_id is not None and hasattr(self, 'scenes_dict'):
      scene_definition = self.scenes_dict.get(scene_id)

  # 传递给 ReferenceImageSelector
  selector_output = await self.reference_image_selector.select_reference_images_and_generate_prompt(
      ...,
      scene_definition=scene_definition,
  )
  ```

### 长期方案（已列入 TODO）：场景环境参考图生成

更可靠的方案是为每个场景预先生成"参考环境图"：

```python
# 流程：
scenes = await scene_planner.plan_scenes(script)

# 为每个场景生成参考环境图
scene_reference_images = {}
for scene in scenes:
    env_image = await generate_scene_environment(
        location=scene.location,
        time_of_day=scene.time_of_day,
        description=scene.description,
        style=style,
    )
    scene_reference_images[scene.scene_id] = env_image

# 后续生成帧时，强制包含对应场景的参考图
```

**优势**：

- 场景环境一致性由参考图硬性保证
- 不依赖 LLM 的"理解"能力
- 可选：结合 ControlNet 等技术进一步增强

**需要实施的内容**：

1. 新增 `agents/scene_environment_generator.py`
2. 在 Pipeline 中增加场景环境图生成阶段
3. 修改 `ReferenceImageSelector` 强制使用场景参考图
4. 可选：集成 ControlNet/深度图技术

**已加入 TODO.md 的 P1 优先级**

## 数据流

### 当前流程（短期方案）

```
Script → ScenePlanner
    ↓
scenes.json (scene_id, location, time_of_day, description)
    ↓
    ├─→ CharacterExtractor (使用 scene_id)
    ├─→ StoryboardArtist (使用 scene_id)
    └─→ Pipeline 保存 scenes_dict
            ↓
        生成帧时:
            1. 根据 shot.scene_id 获取 scene_definition
            2. 传递给 ReferenceImageSelector
            3. 在提示词中加入场景上下文
            4. LLM 生成时考虑场景约束
```

### 未来流程（长期方案）

```
Script → ScenePlanner → scenes.json
    ↓
为每个场景生成环境参考图 → scene_reference_images/
    ↓
生成帧时:
    1. 强制包含对应场景的参考图
    2. 使用 ControlNet 等技术确保空间一致性
    3. 保证同一场景的所有镜头背景完全一致
```

## 优势与局限

### 短期方案的优势

- ✅ 实施成本低，无需额外生成
- ✅ 向后兼容，不影响现有流程
- ✅ 立即生效，提供场景上下文引导

### 短期方案的局限

- ⚠️ 依赖 LLM 的理解和遵守能力（软约束）
- ⚠️ 不能完全保证空间布局一致
- ⚠️ 复杂场景可能出现偏差

### 长期方案的优势

- ✅ 硬性保证场景一致性（参考图）
- ✅ 可结合 ControlNet 等技术
- ✅ 空间布局完全可控

### 长期方案的挑战

- ⚠️ 增加生成环节和成本
- ⚠️ 需要额外的技术集成
- ⚠️ 可能限制镜头的创作灵活性

## 测试建议

1. **多镜头同场景测试**

   - 测试同一场景有多个不同角度/尺寸的镜头
   - 检查背景元素（家具、窗户、装饰）是否一致

2. **场景切换测试**

   - 测试场景 0 → 场景 1 → 场景 0 的跳转
   - 验证重新回到场景 0 时，环境是否与之前一致

3. **时间变化测试**

   - 测试同一地点不同时间（早晨 vs 下午 vs 晚上）
   - 验证光线变化，但布局保持一致

4. **日志验证**
   - 检查 log 中是否输出了场景上下文
   - 验证 `scene_definition` 是否正确传递

## 相关文件

### 修改的文件

- `agents/reference_image_selector.py`：增加场景定义参数和场景上下文构建
- `pipelines/script2video_pipeline.py`：保存场景字典并传递给 ReferenceImageSelector

### 新增的文档

- `docs/TODO.md`：添加了长期方案到 P1 优先级

### 相关接口

- `interfaces/scene.py`：`SceneDefinition` 数据结构

---

**实施日期**: 2025 年 11 月 6 日
**实施方案**: 短期方案（场景上下文增强）
**下一步**: 待规划长期方案（场景环境参考图生成）
