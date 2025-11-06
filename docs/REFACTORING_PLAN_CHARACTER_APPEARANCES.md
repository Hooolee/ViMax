# 角色多外观系统重构计划

## 📋 重构目标

支持角色在不同场景下的**多套外观**（服装、发型、情绪状态等），以提升 AI 视频生成的真实性和一致性。

---

## 🎯 核心问题

### 当前限制

- 每个角色只有一套静态特征和一套动态特征
- 无法处理角色在不同场景的服装变化
- 无法反映角色的情绪状态变化
- 所有场景都使用同一套三视图肖像作为参考

### 目标效果

- 角色可以在不同场景穿不同服装
- 角色可以在不同场景有不同的情绪基调（如疲惫、兴奋）
- 系统能自动为每个场景选择正确的角色外观肖像

---

## 📐 技术方案

### 1. 数据结构重构

#### 1.1 新增 `CharacterAppearance` 类

```python
# interfaces/character.py

from pydantic import BaseModel, Field
from typing import List, Optional

class CharacterAppearance(BaseModel):
    """角色在特定场景的外观"""

    appearance_id: str = Field(
        description="外观ID，格式如 'appearance_0', 'appearance_1'"
    )

    scene_ids: List[int] = Field(
        description="这个外观出现在哪些场景，场景索引从0开始",
        examples=[[0, 1], [2, 3, 4]]
    )

    dynamic_features: str = Field(
        description="可变特征：服装、发型、配饰等",
        examples=[
            "穿着黑色西装，打着深蓝色领带，头发梳理整齐",
            "穿着灰色睡衣，头发凌乱，面容疲惫"
        ]
    )

    emotional_state: Optional[str] = Field(
        default="neutral",
        description="基础情绪状态",
        examples=["neutral", "tired", "energetic", "sad", "angry", "happy"]
    )

    description: Optional[str] = Field(
        default=None,
        description="外观的简短描述，便于识别",
        examples=["工作装束", "居家装束", "运动装束"]
    )
```

#### 1.2 修改 `CharacterInScene` 类

```python
# interfaces/character.py

class CharacterInScene(BaseModel):
    """场景中的角色（修改版）"""

    idx: int = Field(description="角色索引")

    identifier_in_scene: str = Field(
        description="角色标识符（名字或描述性称呼）"
    )

    static_features: str = Field(
        description="静态特征：核心外貌，不随场景变化",
        examples=[
            "男性，30岁左右，东亚人，方脸，浓眉，鹰钩鼻，身高约180cm，体格健壮"
        ]
    )

    # 废弃原有的单一 dynamic_features 字段（保留但标记为deprecated）
    dynamic_features: str = Field(
        default="",
        description="[DEPRECATED] 请使用 appearances 字段",
        deprecated=True
    )

    # 新增：多套外观
    appearances: List[CharacterAppearance] = Field(
        default_factory=list,
        description="角色在不同场景的多套外观"
    )

    def get_appearance_for_scene(self, scene_id: int) -> Optional[CharacterAppearance]:
        """获取指定场景的外观"""
        for appearance in self.appearances:
            if scene_id in appearance.scene_ids:
                return appearance
        # 如果没找到，返回第一个外观（兜底）
        return self.appearances[0] if self.appearances else None
```

#### 1.3 新增角色肖像注册表结构

```python
# 当前结构（简化表示）
character_portraits_registry = {
    "角色A": {
        "front": {"path": "...", "description": "..."},
        "side": {"path": "...", "description": "..."},
        "back": {"path": "...", "description": "..."}
    }
}

# 新结构（支持多外观）
character_portraits_registry = {
    "角色A": {
        "appearance_0": {  # 默认外观
            "front": {"path": "...", "description": "..."},
            "side": {"path": "...", "description": "..."},
            "back": {"path": "...", "description": "..."}
        },
        "appearance_1": {  # 第二套外观
            "front": {"path": "...", "description": "..."},
            "side": {"path": "...", "description": "..."},
            "back": {"path": "...", "description": "..."}
        }
    }
}
```

---

### 2. Agent 重构

#### 2.1 CharacterExtractor (角色提取器) - 🔥 核心重构

**文件**: `agents/character_extractor.py`

**修改点**:

1. **系统提示词升级** (`system_prompt_template_extract_characters`)

   - 新增要求：识别角色在不同场景的外观变化
   - 新增输出：为每个角色提取多套 `CharacterAppearance`
   - 明确指出哪些场景使用哪套外观

2. **输出结构调整**

   ```python
   class ExtractCharactersResponse(BaseModel):
       characters: List[CharacterInScene] = Field(
           ...,
           description="角色列表，每个角色包含多套外观"
       )
   ```

3. **提示词示例**（部分）:

   ```
   [Output]
   For each character, you must:
   1. Extract static_features (unchanging core appearance)
   2. Extract multiple appearances with:
      - appearance_id (e.g., "appearance_0", "appearance_1")
      - scene_ids (which scenes use this appearance)
      - dynamic_features (clothing, accessories for this appearance)
      - emotional_state (optional, e.g., "tired", "energetic")
      - description (brief label, e.g., "work attire", "casual wear")

   Example:
   Character "Alice":
   - static_features: "Female, 25 years old, long brown hair, blue eyes..."
   - appearances:
     - appearance_0: scene_ids=[0,1], dynamic_features="wearing office suit...", emotional_state="neutral"
     - appearance_1: scene_ids=[2,3], dynamic_features="wearing casual jeans and t-shirt...", emotional_state="relaxed"
   ```

**估算工作量**: 🔥🔥🔥 高（2-3 天）

- 重写系统提示词（需要多次测试和调优）
- 修改输出解析逻辑
- 增加外观去重和合并逻辑
- 充分测试提取质量

---

#### 2.2 CharacterPortraitsGenerator (角色肖像生成器) - 🔥 核心重构

**文件**: `agents/character_portraits_generator.py`

**修改点**:

1. **生成多套肖像**

   ```python
   async def generate_portraits_for_appearance(
       self,
       character: CharacterInScene,
       appearance: CharacterAppearance,
       style: str,
   ) -> Dict[str, Dict[str, str]]:
       """为角色的特定外观生成三视图肖像"""
       # 基于 static_features + appearance.dynamic_features + appearance.emotional_state
       # 生成 front/side/back 三张图
   ```

2. **修改提示词**

   - `prompt_template_front`: 增加 `{emotional_state}` 参数
   - 示例: "Generate a portrait with a {emotional_state} expression..."

3. **批量生成接口**
   ```python
   async def generate_all_appearances_for_character(
       self,
       character: CharacterInScene,
       style: str,
   ) -> Dict[str, Dict[str, Dict[str, str]]]:
       """为角色的所有外观生成肖像"""
       results = {}
       for appearance in character.appearances:
           results[appearance.appearance_id] = await self.generate_portraits_for_appearance(
               character, appearance, style
           )
       return results
   ```

**估算工作量**: 🔥🔥 中高（1-2 天）

- 修改生成方法签名
- 调整提示词模板
- 实现批量生成逻辑
- 测试不同情绪状态的生成效果

---

#### 2.3 ReferenceImageSelector (参考图选择器) - 🔥 重要调整

**文件**: `agents/reference_image_selector.py`

**修改点**:

1. **新增场景 ID 参数**

   ```python
   async def select_reference_images_and_generate_prompt(
       self,
       available_image_path_and_text_pairs: List[Tuple[str, str]],
       frame_description: str,
       scene_id: int,  # 新增参数
       characters: List[CharacterInScene],  # 新增参数
       style: str = None,
   ):
   ```

2. **智能过滤肖像**

   - 在选择角色肖像时，根据 `scene_id` 和 `character.get_appearance_for_scene(scene_id)`
   - 只提供该场景对应的外观肖像
   - 过滤掉其他外观的肖像

3. **更新描述文本**
   ```python
   # 示例：为场景2选择参考图时
   # 自动选择 Alice 的 appearance_1（如果scene_id=2在其scene_ids中）
   # 描述变为："Alice wearing casual jeans and t-shirt (appearance_1)"
   ```

**估算工作量**: 🔥 中（1 天）

- 增加参数传递
- 实现外观过滤逻辑
- 更新描述生成

---

#### 2.4 StoryboardArtist (分镜艺术家) - ⚠️ 间接影响

**文件**: `agents/storyboard_artist.py`

**修改点**:

- 在生成分镜时，可以**选择性地**在视觉描述中提及角色的外观特征
- 主要修改系统提示词，提示 AI 注意角色的服装变化

**示例**:

```
When describing a shot, if a character's appearance is notably different from
previous scenes (e.g., changed clothes), explicitly mention it in the visual
description.
```

**估算工作量**: 🟡 低（0.5 天）

- 微调系统提示词
- 可选优化，不影响核心功能

---

### 3. Pipeline 重构

#### 3.1 Script2VideoPipeline - 🔥 关键调整

**文件**: `pipelines/script2video_pipeline.py`

**修改点**:

1. **`generate_character_portraits()` 方法**

   ```python
   async def generate_character_portraits(
       self,
       characters: List[CharacterInScene],
       character_portraits_registry: Optional[Dict],
       style: str,
   ):
       # 遍历每个角色的每个外观
       for character in characters:
           for appearance in character.appearances:
               appearance_key = f"{character.identifier_in_scene}_{appearance.appearance_id}"
               if appearance_key not in character_portraits_registry:
                   # 生成这个外观的三视图
   ```

2. **`generate_frames_for_single_camera()` 方法**

   - 传递 `scene_id` 给 `ReferenceImageSelector`
   - 根据场景 ID 选择正确的角色外观肖像

3. **`generate_portraits_for_single_character()` 方法**
   ```python
   async def generate_portraits_for_single_character(
       self,
       character: CharacterInScene,
       style: str,
   ):
       results = {}
       for appearance in character.appearances:
           character_dir = os.path.join(
               self.working_dir,
               "character_portraits",
               f"{character.idx}_{character.identifier_in_scene}",
               appearance.appearance_id
           )
           os.makedirs(character_dir, exist_ok=True)
           # 为这个外观生成三视图...
   ```

**估算工作量**: 🔥🔥 中高（1.5-2 天）

- 修改多个方法签名
- 调整肖像生成循环逻辑
- 更新参考图选择调用
- 测试整个 pipeline 流程

---

#### 3.2 Idea2VideoPipeline - 🟡 轻微调整

**文件**: `pipelines/idea2video_pipeline.py`

**修改点**:

- 主要变化在于调用 `Script2VideoPipeline` 时传递正确的数据结构
- 确保每个场景的 `scene_id` 正确传递

**估算工作量**: 🟡 低（0.5 天）

---

### 4. 接口和工具类调整

#### 4.1 interfaces/character.py - 🔥 新增类

**修改点**:

- 新增 `CharacterAppearance` 类
- 修改 `CharacterInScene` 类
- 新增工具方法 `get_appearance_for_scene()`

**估算工作量**: 🔥 中（0.5 天）

#### 4.2 保持向后兼容

**策略**:

```python
# 在 CharacterInScene 中保留 dynamic_features 字段
# 如果 appearances 为空，自动从 dynamic_features 创建默认外观
def __post_init__(self):
    if not self.appearances and self.dynamic_features:
        # 创建默认外观（向后兼容）
        self.appearances = [
            CharacterAppearance(
                appearance_id="appearance_0",
                scene_ids=[],  # 适用于所有场景
                dynamic_features=self.dynamic_features,
                emotional_state="neutral",
                description="default"
            )
        ]
```

---

## 📊 影响范围矩阵

| 模块/文件                                 | 影响程度  | 修改类型             | 工作量   |
| ----------------------------------------- | --------- | -------------------- | -------- |
| `interfaces/character.py`                 | 🔥🔥🔥 高 | 新增类、修改类       | 0.5 天   |
| `agents/character_extractor.py`           | 🔥🔥🔥 高 | 重写提示词、修改逻辑 | 2-3 天   |
| `agents/character_portraits_generator.py` | 🔥🔥🔥 高 | 重构生成方法         | 1-2 天   |
| `agents/reference_image_selector.py`      | 🔥🔥 中高 | 增加参数、过滤逻辑   | 1 天     |
| `agents/storyboard_artist.py`             | 🟡 低     | 微调提示词（可选）   | 0.5 天   |
| `pipelines/script2video_pipeline.py`      | 🔥🔥 中高 | 调整多个方法         | 1.5-2 天 |
| `pipelines/idea2video_pipeline.py`        | 🟡 低     | 参数传递             | 0.5 天   |
| `agents/best_image_selector.py`           | ✅ 无     | 无需修改             | 0 天     |
| `agents/camera_image_generator.py`        | ✅ 无     | 无需修改             | 0 天     |
| 测试和调优                                | 🔥🔥🔥 高 | 端到端测试           | 2-3 天   |

**总计工作量**: 约 **9-13 个工作日**（1.5-2.5 周）

---

## 🛠️ 实施步骤

### Phase 1: 数据结构准备（1 天）

- [ ] 新增 `CharacterAppearance` 类
- [ ] 修改 `CharacterInScene` 类
- [ ] 实现向后兼容逻辑
- [ ] 编写单元测试

### Phase 2: 核心 Agent 重构（5-7 天）

- [ ] 重构 `CharacterExtractor`
  - [ ] 重写系统提示词
  - [ ] 调整输出解析
  - [ ] 测试多外观提取质量
- [ ] 重构 `CharacterPortraitsGenerator`
  - [ ] 修改生成方法
  - [ ] 调整提示词模板
  - [ ] 实现批量生成
  - [ ] 测试不同情绪状态

### Phase 3: Pipeline 调整（2-3 天）

- [ ] 修改 `Script2VideoPipeline`
  - [ ] 调整肖像生成流程
  - [ ] 更新参考图选择调用
  - [ ] 测试场景外观匹配
- [ ] 修改 `ReferenceImageSelector`
  - [ ] 增加场景 ID 参数
  - [ ] 实现外观过滤
- [ ] 轻微调整 `Idea2VideoPipeline`

### Phase 4: 集成测试（2-3 天）

- [ ] 端到端测试（简单场景）
- [ ] 端到端测试（复杂场景，多外观变化）
- [ ] 性能测试
- [ ] 边界情况测试
- [ ] 向后兼容性测试

### Phase 5: 文档和优化（1 天）

- [ ] 更新 API 文档
- [ ] 更新用户文档
- [ ] 代码注释完善
- [ ] 性能优化（如有需要）

---

## 🎯 验收标准

### 功能验收

- ✅ 系统能正确提取角色的多套外观
- ✅ 为每套外观生成独立的三视图肖像
- ✅ 在生成镜头时自动选择正确场景的外观肖像
- ✅ 支持至少 3 种情绪状态（neutral, tired, happy）
- ✅ 向后兼容旧的单外观数据格式

### 质量验收

- ✅ 角色在不同场景的服装正确匹配剧本描述
- ✅ 角色的核心外貌（静态特征）在所有场景保持一致
- ✅ 情绪状态在肖像中有明显体现
- ✅ 无性能显著下降（生成时间增加<30%）

### 测试用例

1. **简单测试**: 2 个角色，2 个场景，每个角色 1 套外观
2. **中等测试**: 3 个角色，4 个场景，主角 2 套外观，配角 1 套外观
3. **复杂测试**: 5 个角色，8 个场景，主角 3 套外观，配角 1-2 套外观
4. **边界测试**: 角色在某个场景没有明确外观描述（应使用默认外观）
5. **兼容测试**: 使用旧格式的角色数据（只有单一 dynamic_features）

---

## ⚠️ 风险和挑战

### 1. LLM 提取质量 🔥

**风险**: LLM 可能无法准确识别角色的外观变化
**缓解措施**:

- 提供详细的 few-shot 示例
- 增加多轮验证机制
- 允许用户手动修正提取结果

### 2. 肖像生成成本 💰

**风险**: 多外观会导致图像生成成本成倍增加
**缓解措施**:

- 实现智能外观合并（相似外观复用）
- 提供"精简模式"（只生成关键外观）
- 懒加载策略（按需生成外观肖像）

### 3. 向后兼容性 🔄

**风险**: 可能破坏现有代码和数据
**缓解措施**:

- 保留旧字段并标记为 deprecated
- 实现自动迁移逻辑
- 充分的回归测试

### 4. 性能影响 ⏱️

**风险**: 处理时间可能显著增加
**缓解措施**:

- 并行生成多个外观的肖像
- 优化缓存策略
- 性能监控和基准测试

---

## 📈 后续优化方向

### 短期（1 个月内）

- 支持角色外观的自动补全（如果剧本缺少描述）
- 实现外观相似度检测（自动合并相似外观）
- 增加外观预览功能

### 中期（3 个月内）

- 支持更细粒度的情绪状态（不仅是基础状态，还有强度）
- 实现角色关系图谱（影响角色间的互动）
- 支持用户手动上传角色外观参考图

### 长期（6 个月+）

- 支持角色外观的动态演变（如逐渐变老、变脏等）
- 实现服装/道具库系统
- 支持角色动作模板库

---

## 📝 相关文档

- [AGENT_LOGIC_ANALYSIS.md](./AGENT_LOGIC_ANALYSIS.md) - Agent 逻辑分析
- [ARCHITECTURE_ZH.md](./ARCHITECTURE_ZH.md) - 系统架构文档
- [STYLE_CONSISTENCY_WORKFLOW.md](./STYLE_CONSISTENCY_WORKFLOW.md) - 风格一致性工作流

---

## 👥 需要协作的团队

- **AI/Prompt 工程师**: 优化 CharacterExtractor 的提示词
- **后端开发**: 实现数据结构和 Pipeline 调整
- **QA**: 设计和执行测试用例
- **产品经理**: 定义优先级和验收标准

---

## 📅 时间规划建议

| 周     | 任务                            | 产出                                        |
| ------ | ------------------------------- | ------------------------------------------- |
| Week 1 | Phase 1 + Phase 2 (部分)        | 数据结构 + CharacterExtractor               |
| Week 2 | Phase 2 (完成) + Phase 3 (开始) | CharacterPortraitsGenerator + Pipeline 调整 |
| Week 3 | Phase 3 (完成) + Phase 4        | Pipeline 完成 + 集成测试                    |

---

**文档版本**: 1.0  
**创建日期**: 2025-01-06  
**最后更新**: 2025-01-06  
**负责人**: [待定]  
**状态**: 📋 待批准
