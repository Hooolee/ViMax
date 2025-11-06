# 场景划分统一管理 - 实施说明

## 问题背景

在之前的实现中，存在一个严重的逻辑问题：

- **CharacterExtractor** 在提取人物时，会根据剧本自行识别场景，并为每个人物外观分配 `scene_ids`
- **StoryboardArtist** 在生成分镜时，也会根据剧本自行识别场景，并为每个镜头分配 `scene_id`

**核心矛盾**：两个 Agent 对"场景"的理解可能不一致，导致：

- 人物外观的 `scene_ids` 和分镜的 `scene_id` 不匹配
- 在生成帧图像时选择错误的人物肖像
- 人物服装/发型不符合场景要求
- 外观连续性问题

## 解决方案

采用**预先统一场景划分**的方案：

1. 新增 `ScenePlanner` Agent，负责从剧本中分析和划分场景
2. 所有后续流程（人物提取、分镜生成）都使用这个统一的场景定义
3. 确保整个 pipeline 中的 `scene_id` 保持一致

## 实施细节

### 1. 新增 SceneDefinition 数据结构

**文件**: `interfaces/scene.py`

```python
class SceneDefinition(BaseModel):
    scene_id: int  # 场景ID，从0开始
    location: str  # 场景地点
    time_of_day: Optional[str]  # 时间段
    description: str  # 场景简短描述
    script_excerpt: Optional[str]  # 对应的剧本片段
```

### 2. 新增 ScenePlanner Agent

**文件**: `agents/scene_planner.py`

**功能**:

- 分析剧本并识别不同场景（基于地点和时间变化）
- 为每个场景分配唯一的 `scene_id`（从 0 开始）
- 返回场景列表及描述

**关键方法**:

```python
async def plan_scenes(self, script: str) -> List[SceneDefinition]
```

### 3. 更新 CharacterExtractor

**文件**: `agents/character_extractor.py`

**改动**:

- `extract_characters()` 方法新增 `scenes` 参数
- 在提示词中加入预定义的场景列表
- 确保提取的人物外观使用统一的 `scene_id`

```python
async def extract_characters(
    self,
    script: str,
    scenes: List[SceneDefinition] = None,
) -> List[CharacterInScene]
```

### 4. 更新 StoryboardArtist

**文件**: `agents/storyboard_artist.py`

**改动**:

- `design_storyboard()` 方法新增 `scenes` 参数
- 在提示词中加入预定义的场景列表
- 要求 LLM 使用预定义的 `scene_id` 为镜头分配场景

```python
async def design_storyboard(
    self,
    script: str,
    characters: List[CharacterInScene],
    scenes: List[SceneDefinition] = None,
    user_requirement: Optional[str] = None,
    retry_timeout: int = 150,
) -> List[ShotBriefDescription]
```

### 5. 更新 Script2VideoPipeline

**文件**: `pipelines/script2video_pipeline.py`

**新流程**:

```
1. plan_scenes()           # 统一场景划分
   ↓
2. extract_characters()    # 使用统一的场景定义提取人物
   ↓
3. generate_character_portraits()  # 生成人物肖像
   ↓
4. design_storyboard()     # 使用统一的场景定义生成分镜
   ↓
5. 后续流程...
```

**关键改动**:

- 初始化时添加 `ScenePlanner`
- 在 `__call__` 方法开始时先进行场景划分
- 将场景信息传递给 `extract_characters` 和 `design_storyboard`
- 场景定义保存在 `scenes.json`

## 数据流示意

```
Script (剧本)
    ↓
ScenePlanner.plan_scenes()
    ↓
scenes.json
    ├─→ CharacterExtractor.extract_characters(scenes)
    │       ↓
    │   characters.json (包含正确的 scene_ids)
    │       ↓
    │   CharacterPortraitsGenerator
    │       ↓
    │   character_portraits_registry.json
    │
    └─→ StoryboardArtist.design_storyboard(scenes)
            ↓
        storyboard.json (包含正确的 scene_id)
            ↓
        后续生成流程（scene_id 一致性得到保证）
```

## 优势

1. **一致性保证**: 所有 Agent 使用相同的场景定义，避免 `scene_id` 冲突
2. **可追溯性**: 场景划分单独保存，便于调试和验证
3. **灵活性**: 如果场景划分有误，只需修改 `scenes.json` 并重新运行后续流程
4. **向后兼容**: 保留了 `scenes=None` 的选项，允许 Agent 独立识别场景（但不推荐）

## 注意事项

1. **scene_id 必须连续**: ScenePlanner 会验证并自动修复非连续的 scene_id
2. **场景数量**: 对于单场景剧本，会创建一个 `scene_id=0` 的场景
3. **缓存机制**: 场景定义会缓存在 `scenes.json`，删除该文件可重新生成
4. **日志输出**: 新增了详细的日志，便于追踪场景划分和使用情况

## 测试建议

1. **单场景测试**: 测试只有一个场景的剧本
2. **多场景测试**: 测试包含多个场景（不同地点/时间）的剧本
3. **外观变化测试**: 测试人物在不同场景有不同外观的情况
4. **一致性验证**: 检查生成的 `scenes.json`, `characters.json`, `storyboard.json` 中的 scene_id 是否一致

## 未来改进

1. 可以考虑在 ScenePlanner 中加入场景时长估计
2. 可以考虑支持场景内的时间跳跃（sub-scene）
3. 可以考虑加入场景转场效果的建议

---

**实施日期**: 2025 年 11 月 6 日
**相关分支**: feat-multi-appearance
**影响范围**:

- 新增: `agents/scene_planner.py`, `interfaces/scene.py` 中的 `SceneDefinition`
- 修改: `agents/character_extractor.py`, `agents/storyboard_artist.py`, `pipelines/script2video_pipeline.py`
