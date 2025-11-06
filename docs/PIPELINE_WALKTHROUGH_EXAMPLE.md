# ViMax Pipeline 完整流程示例

本文档通过一个具体案例，详细展示 ViMax 从剧本到最终视频的完整工作流程。

---

## 📝 示例剧本

```
INT. 办公室 - 白天

John坐在办公桌前办公，听到敲门声，他转头看过去，发现是下属小王拿着文件站在门口。
```

---

## 🎬 完整处理流程（8 个阶段）

### 阶段 0: 场景规划 (ScenePlanner)

#### 输入

- 剧本文本

#### 处理

```python
scenes = await scene_planner.plan_scenes(script)
```

#### 输出 → `scenes.json`

```json
[
  {
    "scene_id": 0,
    "location": "办公室内部 / Office Interior",
    "time_of_day": "白天 / Daytime",
    "description": "John working at desk, Wang arrives with documents",
    "script_excerpt": "INT. 办公室 - 白天..."
  }
]
```

**关键产物**:

- ✅ `scene_id=0` 确定
- ✅ 所有后续 Agent 都会使用这个统一的 scene_id
- ✅ 避免了 CharacterExtractor 和 StoryboardArtist 对场景理解不一致的问题

---

### 阶段 1: 角色提取 (CharacterExtractor)

#### 输入

- 剧本
- **scenes** (来自阶段 0) 🔗

#### 处理

```python
characters = await character_extractor.extract_characters(
    script=script,
    scenes=scenes  # 使用统一的场景定义
)
```

#### 输出 → `characters.json`

```json
[
  {
    "idx": 0,
    "identifier_in_scene": "John",
    "static_features": "Male, 35 years old, brown hair, professional appearance",
    "appearances": [
      {
        "appearance_id": "appearance_0",
        "scene_ids": [0], // ← 关键：使用 ScenePlanner 的 scene_id
        "dynamic_features": "Dark blue business suit, white shirt, black tie",
        "emotional_state": "focused",
        "description": "Office professional attire"
      }
    ]
  },
  {
    "idx": 1,
    "identifier_in_scene": "小王 (Wang)",
    "static_features": "Male, 28 years old, short black hair, slim build",
    "appearances": [
      {
        "appearance_id": "appearance_0",
        "scene_ids": [0], // ← 关键：与 John 使用相同的 scene_id
        "dynamic_features": "Gray suit, holding documents folder",
        "emotional_state": "nervous",
        "description": "Junior staff office attire"
      }
    ]
  }
]
```

**关键设计**:

- 每个角色可以有多个 `appearances`（不同场景的不同外观）
- 每个 `appearance` 都标记了 `scene_ids`，明确该外观适用于哪些场景
- 在本例中，两个角色都只有一套外观（`appearance_0`），都适用于场景 0

---

### 阶段 2: 生成角色肖像 (CharacterPortraitsGenerator)

#### 输入

- characters (来自阶段 1)
- style = "Realistic Anime"

#### 处理

```python
for character in characters:
    portraits = await character_portraits_generator.generate_all_appearances_for_character(
        character=character,
        style=style
    )
```

#### 输出 → 文件系统

```
character_portraits/
├── 0_John/
│   └── appearance_0/        # ← 对应 scene_id=0 的外观
│       ├── front.png        # John 穿深蓝西装的正面全身肖像
│       ├── side.png         # John 穿深蓝西装的侧面全身肖像
│       └── back.png         # John 穿深蓝西装的背面全身肖像
└── 1_Wang/
    └── appearance_0/        # ← 对应 scene_id=0 的外观
        ├── front.png        # 小王穿灰西装拿文件的正面肖像
        ├── side.png         # 小王穿灰西装拿文件的侧面肖像
        └── back.png         # 小王穿灰西装拿文件的背面肖像
```

**生成的图像特点**:

- ✅ 纯白背景，便于后续合成
- ✅ 全身居中构图
- ✅ 基于 `emotional_state` 自动应用表情（John: focused, Wang: nervous）
- ✅ 三视图确保任何拍摄角度都有合适的参考

**示例描述**:

- `0_John/appearance_0/front.png`:
  - 35 岁男性，棕色头发
  - 穿深蓝色商务西装、白衬衫、黑领带
  - 面部专注表情
  - 全身居中，纯白背景
  - 风格：Realistic Anime

---

### 阶段 3: 设计分镜 (StoryboardArtist)

#### 输入

- script
- characters
- **scenes** (来自阶段 0) 🔗

#### 处理

```python
shot_briefs = await storyboard_artist.design_storyboard(
    script=script,
    characters=characters,
    scenes=scenes  # 使用统一的场景定义
)
```

#### 输出 → `storyboard_brief.json`

```json
[
  {
    "idx": 0,
    "scene_id": 0, // ← 关键：使用 ScenePlanner 的 scene_id
    "shot_size": "medium",
    "angle": "eye_level",
    "lens_equiv_mm": 50,
    "screen_direction": "static",
    "visual_desc": "John sits at his desk, focused on his computer. The office is well-lit with natural daylight.",
    "audio_desc": "Ambient office sounds, keyboard typing",
    "duration_sec_estimate": 3
  },
  {
    "idx": 1,
    "scene_id": 0,
    "shot_size": "close_up",
    "angle": "eye_level",
    "lens_equiv_mm": 85,
    "screen_direction": "static",
    "visual_desc": "Close-up of John's face, he hears something and pauses.",
    "audio_desc": "Knock on door sound (off-screen)",
    "duration_sec_estimate": 2
  },
  {
    "idx": 2,
    "scene_id": 0,
    "shot_size": "medium",
    "angle": "eye_level",
    "lens_equiv_mm": 50,
    "screen_direction": "left_to_right",
    "visual_desc": "John turns his head from the computer towards the door.",
    "audio_desc": "Chair slightly creaking",
    "duration_sec_estimate": 2
  },
  {
    "idx": 3,
    "scene_id": 0,
    "shot_size": "full_shot",
    "angle": "eye_level",
    "lens_equiv_mm": 35,
    "screen_direction": "static",
    "visual_desc": "Wang stands at the doorway, holding documents, looking nervous.",
    "audio_desc": "Footsteps stopping",
    "duration_sec_estimate": 3
  }
]
```

**分镜设计思路**:

1. **镜头 0**: 建立场景 - 中景展示 John 在办公桌前工作
2. **镜头 1**: 特写 - 突出 John 听到敲门声的反应
3. **镜头 2**: 中景 - 展示 John 转头的动作
4. **镜头 3**: 全景 - 展示小王在门口的全貌

---

### 阶段 4: 分解视觉描述 (StoryboardArtist)

#### 输入

- shot_briefs (来自阶段 3)
- characters

#### 处理

```python
shot_descriptions = []
for brief in shot_briefs:
    detailed = await storyboard_artist.decompose_visual_description(
        shot_brief_desc=brief,
        characters=characters
    )
    shot_descriptions.append(detailed)
```

#### 输出 → `storyboard_detailed.json` (以镜头 2 为例)

```json
{
  "idx": 2,
  "scene_id": 0, // ← 保留 scene_id
  "shot_size": "medium",
  "cam_idx": 0,

  // 首帧描述
  "ff_desc": "John sits at desk facing computer, office interior visible with wooden desk, computer monitor, windows with daylight",
  "ff_vis_char_idxs": [0], // John 出现

  // 末帧描述
  "lf_desc": "John's head turned towards door, upper body rotated, office interior same with desk and windows",
  "lf_vis_char_idxs": [0], // John 仍然出现

  // 运动描述
  "motion_desc": "John smoothly rotates his head and upper body from facing computer screen to facing the door direction. Camera remains static.",

  // 变化程度
  "variation_type": "medium", // 首帧和末帧有中等程度的变化

  "visual_desc": "John turns his head from the computer towards the door.",
  "audio_desc": "Chair slightly creaking",
  "angle": "eye_level",
  "lens_equiv_mm": 50,
  "screen_direction": "left_to_right",
  "duration_sec_estimate": 2
}
```

**关键设计**:

- `ff_desc` (首帧描述): 静态的起始画面
- `lf_desc` (末帧描述): 静态的结束画面
- `motion_desc` (运动描述): 首末帧之间的动态变化
- `variation_type`: 指导是否需要生成末帧
  - `small`: 只生成首帧（变化很小，视频生成器可以处理）
  - `medium/large`: 需要生成首帧和末帧

---

### 阶段 5: 构建镜头树 (CameraImageGenerator)

#### 输入

- shot_descriptions

#### 处理

```python
camera_tree = await camera_image_generator.construct_camera_tree(
    cameras=cameras,
    shot_descs=shot_descriptions
)
```

#### 输出 → `camera_tree.json`

```json
[
  {
    "idx": 0,
    "active_shot_idxs": [0, 2], // Camera 0 拍摄镜头 0 和 2
    "parent_shot_idx": null, // 根镜头，无父镜头
    "parent_cam_idx": null,
    "missing_info": null
  },
  {
    "idx": 1,
    "active_shot_idxs": [1], // Camera 1 拍摄镜头 1（特写）
    "parent_shot_idx": 0, // 父镜头是镜头 0（从中景切到特写）
    "parent_cam_idx": 0,
    "missing_info": null
  },
  {
    "idx": 2,
    "active_shot_idxs": [3], // Camera 2 拍摄镜头 3（全景）
    "parent_shot_idx": 0, // 父镜头是镜头 0
    "parent_cam_idx": 0,
    "missing_info": null
  }
]
```

**镜头树的作用**:

- 建立镜头之间的层级关系
- 决定生成顺序（先生成父镜头，再生成子镜头）
- 子镜头可以复用父镜头的环境信息
- 如果 `missing_info` 不为空，需要生成过渡视频来获得新视角

---

### 阶段 6: 连续性检查

#### 处理

```python
continuity_report = check_continuity(shot_descriptions, camera_tree)
```

#### 输出 → `continuity_report.json`

```json
{
  "passed": true,
  "violations": []
}
```

**检查内容**:

- ✅ 180 度法则：确保镜头切换不会混淆观众的空间感
- ✅ 30 度法则：确保镜头切换有足够的角度变化
- ✅ 运动方向一致性：确保角色运动方向在连续镜头中保持一致

如果检查失败，会输出详细的违规信息并终止生成。

---

### 阶段 7: 生成帧和视频 ⭐ 核心阶段 ⭐

这是 **ReferenceImageSelector 发挥关键作用的阶段**！

---

#### 📸 镜头 0 - 首帧生成

##### Step 1: 收集可用参考图

Pipeline 收集所有可能用到的参考图：

```python
available_image_path_and_text_pairs = [
    # John 的三视图
    ("character_portraits/0_John/appearance_0/front.png",
     "John front view: male, brown hair, dark blue business suit, focused expression"),
    ("character_portraits/0_John/appearance_0/side.png",
     "John side view: male, brown hair, dark blue business suit, focused expression"),
    ("character_portraits/0_John/appearance_0/back.png",
     "John back view: male, brown hair, dark blue business suit"),

    # Wang 的三视图
    ("character_portraits/1_Wang/appearance_0/front.png",
     "Wang front view: male, short black hair, gray suit, holding documents, nervous expression"),
    ("character_portraits/1_Wang/appearance_0/side.png",
     "Wang side view: male, short black hair, gray suit, holding documents"),
    ("character_portraits/1_Wang/appearance_0/back.png",
     "Wang back view: male, short black hair, gray suit"),
]
```

##### Step 2: ReferenceImageSelector 智能选择

```python
selector_output = await reference_image_selector.select_reference_images_and_generate_prompt(
    available_image_path_and_text_pairs=available_image_path_and_text_pairs,
    frame_description="John sits at desk facing computer, office interior visible",
    style="Realistic Anime",
    scene_id=0,  # ← 传入场景 ID
    characters=[john, wang],
    scene_definition=SceneDefinition(
        scene_id=0,
        location="办公室内部",
        time_of_day="白天",
        description="John working at desk"
    )
)
```

**内部处理流程**:

**2.1 场景上下文构建**

```python
scene_context = """
Current scene context:
- Location: 办公室内部 / Office Interior
- Time of day: 白天 / Daytime
- Scene description: John working at desk
"""
```

**2.2 场景外观过滤** (`_filter_images_by_scene`)

```python
# 检查每张肖像的 appearance.scene_ids 是否包含当前 scene_id=0

# John 的 appearance_0.scene_ids = [0] → ✓ 保留
filtered_images = [
    "character_portraits/0_John/appearance_0/front.png",  # ✓
    "character_portraits/0_John/appearance_0/side.png",   # ✓
    "character_portraits/0_John/appearance_0/back.png",   # ✓
]

# Wang 的 appearance_0.scene_ids = [0] → ✓ 保留
filtered_images += [
    "character_portraits/1_Wang/appearance_0/front.png",  # ✓
    "character_portraits/1_Wang/appearance_0/side.png",   # ✓
    "character_portraits/1_Wang/appearance_0/back.png",   # ✓
]

# 结果：所有 6 张图都保留（因为都属于场景 0）
```

**2.3 多模态智能选择**

LLM 分析帧描述 "John sits at desk facing computer"：

- ✅ 需要：John 的肖像（他是主角）
- ✅ 需要：侧面或侧正面视角（他面对电脑，不是正对镜头）
- ❌ 不需要：Wang 的肖像（他还没出现）

```python
selected_images = [
    ("character_portraits/0_John/appearance_0/side.png",
     "John side view in business suit"),
]
```

**2.4 生成详细提示词**

```python
text_prompt = """
Scene Context: Office Interior, Daytime, John working at desk

Generate an image showing:
A professional office interior during daytime with natural lighting from windows.
John (reference Image 0: male, 35 years old, brown hair, dark blue business suit,
white shirt, black tie, focused expression) sits at a wooden desk facing a computer
screen. He is shown from a side angle, concentrating on his work.

The office has:
- Modern wooden desk with computer monitor
- Office chair
- Windows showing daylight
- Professional office atmosphere

Character appearance must strictly match Image 0 for:
- Facial features (brown hair, facial structure)
- Clothing (dark blue suit, white shirt, black tie)
- Expression (focused, professional)
- Body posture (sitting, working)

Style: Realistic Anime
Composition: Medium shot, side angle
"""
```

**2.5 提示词验证**

系统自动检查：

- ✅ 是否明确引用了 "Image 0"
- ✅ 是否包含场景上下文
- ✅ 是否包含风格要求

##### Step 3: ImageGenerator 生成候选图

```python
candidates = []
for i in range(3):  # 生成 3 张候选
    candidate = await image_generator.generate_single_image(
        prompt=text_prompt,
        reference_image_paths=["character_portraits/0_John/appearance_0/side.png"],
        size="1600x900"
    )
    candidates.append(candidate)
    # 保存为: shots/0/first_frame_candidate_0.png, _1.png, _2.png
```

**生成的候选图**:

- **Candidate 0**: John 侧面坐在桌前，构图稍微偏左，光线正常
- **Candidate 1**: John 侧面坐在桌前，构图居中，光线更好 ⭐
- **Candidate 2**: John 侧面坐在桌前，构图偏右，桌子细节丰富

##### Step 4: BestImageSelector 选择最佳

```python
best_image_path = await best_image_selector(
    reference_image_path_and_text_pairs=[
        ("character_portraits/0_John/appearance_0/side.png", "John side view in business suit")
    ],
    target_description="John sits at desk facing computer, office interior visible",
    candidate_image_paths=[
        "shots/0/first_frame_candidate_0.png",
        "shots/0/first_frame_candidate_1.png",
        "shots/0/first_frame_candidate_2.png"
    ]
)
# 返回: "shots/0/first_frame_candidate_1.png" (评估为最佳)
```

**评估标准**:

1. ✅ 角色一致性（面部、服装、姿态与参考图匹配）
2. ✅ 空间一致性（场景布局合理）
3. ✅ 描述准确性（包含了所有关键元素）
4. ✅ 质量因素（无白边、黑边、额外边框）

##### Step 5: 保存最终帧

```python
shutil.copy(
    "shots/0/first_frame_candidate_1.png",
    "shots/0/first_frame.png"
)
```

**输出**: `shots/0/first_frame.png` ✅

---

#### 📸 镜头 2 - 首帧生成（John 转头前）

##### Step 1: 收集可用参考图

```python
available_image_path_and_text_pairs = [
    # 角色肖像（与镜头 0 相同）
    ("character_portraits/0_John/appearance_0/front.png", "..."),
    ("character_portraits/0_John/appearance_0/side.png", "..."),
    ("character_portraits/0_John/appearance_0/back.png", "..."),

    # ⭐ 新增：已生成的帧（用于保持场景一致性）
    ("shots/0/first_frame.png",
     "John sits at desk facing computer, office interior with wooden desk and windows"),
]
```

##### Step 2: ReferenceImageSelector 智能选择

帧描述: "John sits at desk facing computer, office interior visible"

**选择的参考图**:

```python
selected_images = [
    ("shots/0/first_frame.png", "Office interior with John at desk"),  # 保持环境一致
    ("character_portraits/0_John/appearance_0/side.png", "John appearance"),  # 确保外貌一致
]
```

**生成的提示词**:

```python
text_prompt = """
Scene Context: Office Interior, Daytime, John working at desk

Generate an image showing:
The exact same office interior as Image 0 (wooden desk, computer monitor, windows
with daylight, professional office atmosphere).

John (reference Image 1 for appearance: male, brown hair, dark blue business suit)
sits at the desk in the same position as Image 0, facing the computer screen.

CRITICAL: Maintain perfect consistency with Image 0 for:
- Office layout (desk position, window placement)
- Furniture (exact same desk and chair)
- Lighting (same daylight from windows)
- John's clothing (dark blue suit, white shirt, black tie)
- John's posture (sitting, working at computer)

The scene should look like it's from the same continuous shot as Image 0.

Style: Realistic Anime
"""
```

##### Step 3-5: 生成候选图 → 选择最佳 → 保存

**输出**: `shots/2/first_frame.png` ✅

---

#### 📸 镜头 2 - 末帧生成（John 转头后）

##### Step 1: 收集可用参考图

```python
available_image_path_and_text_pairs = [
    ("character_portraits/0_John/appearance_0/front.png", "John front view"),
    ("character_portraits/0_John/appearance_0/side.png", "John side view"),

    # 环境参考
    ("shots/0/first_frame.png", "Office interior"),

    # ⭐ 本镜头的首帧（最重要的参考）
    ("shots/2/first_frame.png", "John at desk facing computer"),
]
```

##### Step 2: ReferenceImageSelector 智能选择

帧描述: "John's head turned towards door, upper body rotated, office interior same"

**选择的参考图**:

```python
selected_images = [
    ("shots/2/first_frame.png", "Environment and initial posture"),  # 保持环境和姿势连贯
    ("character_portraits/0_John/appearance_0/front.png", "John frontal appearance"),  # 转头后接近正面
]
```

**生成的提示词**:

```python
text_prompt = """
Scene Context: Office Interior, Daytime, John working at desk

Generate an image showing:
The exact same office scene as Image 0, but John has turned his head and upper body
from facing the computer to looking towards the door (screen right direction).

John (reference Image 1 for facial features and clothing: male, brown hair, dark blue
business suit, white shirt, black tie) maintains the same professional appearance but
with his face now visible from a more frontal angle.

Key changes from Image 0:
- John's head rotated towards door (right side of frame)
- Upper body slightly rotated
- Face visible from front/three-quarter angle

Must remain EXACTLY the same as Image 0:
- Office environment (desk, computer, windows, lighting)
- John's clothing (suit, shirt, tie)
- Desk and chair position
- Overall scene atmosphere

Style: Realistic Anime
"""
```

##### Step 3-5: 生成候选图 → 选择最佳 → 保存

**输出**: `shots/2/last_frame.png` ✅

---

#### 📸 镜头 3 - 首帧生成（小王登场）

##### Step 1: 收集可用参考图

```python
available_image_path_and_text_pairs = [
    # John 的肖像
    ("character_portraits/0_John/appearance_0/front.png", "..."),

    # ⭐ Wang 的肖像（首次使用）
    ("character_portraits/1_Wang/appearance_0/front.png",
     "Wang front view: gray suit, holding documents, nervous expression"),
    ("character_portraits/1_Wang/appearance_0/side.png", "Wang side view"),

    # 环境参考
    ("shots/0/first_frame.png", "Office interior"),
    ("shots/2/first_frame.png", "Office interior"),
    ("shots/2/last_frame.png", "John turned towards door"),
]
```

##### Step 2: ReferenceImageSelector 智能选择

帧描述: "Wang stands at the doorway, holding documents, looking nervous"

**选择的参考图**:

```python
selected_images = [
    ("shots/0/first_frame.png", "Office environment reference"),
    ("character_portraits/1_Wang/appearance_0/front.png", "Wang appearance"),
]
```

**生成的提示词**:

```python
text_prompt = """
Scene Context: Office Interior, Daytime, John working at desk

Generate a wider shot of the office interior (reference Image 0 for environment:
wooden desk, windows, professional office atmosphere, daytime lighting).

Wang (reference Image 1: male, 28 years old, short black hair, gray suit,
holding documents folder in hands, nervous expression) stands at the doorway
in the background/middle ground, visible through the open door frame.

Scene composition:
- Wider angle showing more of the office (full shot)
- Wang visible at doorway (standing, holding documents)
- Office environment consistent with Image 0
- Natural daylight from windows

Wang's appearance must strictly match Image 1:
- Facial features (short black hair, young male face)
- Clothing (gray suit)
- Props (documents folder in hands)
- Expression (nervous, somewhat hesitant)

Style: Realistic Anime
"""
```

##### Step 3-5: 生成候选图 → 选择最佳 → 保存

**输出**: `shots/3/first_frame.png` ✅

---

#### 🎥 生成视频

对于需要生成末帧的镜头（`variation_type` = "medium" 或 "large"），使用首帧和末帧生成视频：

##### 镜头 2 的视频生成

```python
video_output = await video_generator.generate_single_video(
    prompt="John smoothly rotates his head and upper body from facing the computer to looking towards the door. Camera remains static. Professional office setting.",
    reference_image_paths=[
        "shots/2/first_frame.png",  # 起始帧：John 看电脑
        "shots/2/last_frame.png",   # 结束帧：John 转头看门
    ]
)
# 保存为: shots/2/video.mp4
```

**生成的视频内容**:

- 时长：约 2 秒
- 内容：John 从看电脑平滑转头到看向门口
- 特点：保持办公室环境不变，只有 John 的头部和上身运动

##### 其他镜头的视频生成

对于 `variation_type` = "small" 的镜头，只用首帧生成视频：

```python
# 镜头 0 和 3
video_output = await video_generator.generate_single_video(
    prompt=shot_description.motion_desc + "\n" + shot_description.audio_desc,
    reference_image_paths=[
        "shots/0/first_frame.png"  # 只提供首帧
    ]
)
```

---

### 阶段 8: 时间线渲染

#### 输入

- 所有生成的视频片段

#### 处理

```python
# 构建时间线
timeline = build_timeline(shot_descriptions, working_dir)

# 写入 EDL (Edit Decision List)
write_timeline_edl(timeline, "timeline.edl")

# 渲染最终视频
render_timeline(timeline, "final_video.mp4")
```

#### 输出 → `final_video.mp4`

**时间线结构**:

```
[0.0 - 3.0秒] 镜头 0: John 坐在桌前办公
[3.0 - 5.0秒] 镜头 1: John 面部特写，听到敲门声
[5.0 - 7.0秒] 镜头 2: John 转头看向门口
[7.0 - 10.0秒] 镜头 3: 小王站在门口拿着文件
```

**最终视频效果**:

- ✅ 角色外貌完全一致（John 的发型、服装、面部特征在所有镜头中保持不变）
- ✅ 场景环境一致（办公室的布局、光线、氛围保持不变）
- ✅ 动作流畅自然（镜头切换符合电影语言规则）
- ✅ 音画同步（音效与画面匹配）

---

## 🎯 ReferenceImageSelector 的核心作用总结

### 在每个镜头生成中的角色

| 镜头            | 输入参考图            | ReferenceImageSelector 选择 | 目的                            |
| --------------- | --------------------- | --------------------------- | ------------------------------- |
| **镜头 0 首帧** | 6 张角色肖像          | John 侧面肖像               | 建立 John 的外貌基准            |
| **镜头 2 首帧** | 6 张肖像 + 1 张环境图 | 环境图 + John 肖像          | 保持环境一致 + John 外貌一致    |
| **镜头 2 末帧** | 6 张肖像 + 3 张环境图 | 本镜头首帧 + John 正面肖像  | 保持连贯性 + 转头后的面部细节   |
| **镜头 3 首帧** | 所有肖像 + 所有环境图 | 环境图 + Wang 肖像          | 保持环境一致 + 引入 Wang 的外貌 |

### 核心价值

#### 1. 角色一致性 ⭐⭐⭐⭐⭐

- ✅ 确保 John 在所有镜头中的发型、面部特征、服装完全一致
- ✅ 确保 Wang 的外貌符合角色设定
- ✅ 通过 `scene_id` 自动选择正确的角色外观（如果角色在不同场景有不同服装）

#### 2. 场景一致性 ⭐⭐⭐⭐⭐

- ✅ 确保办公室的布局、家具、窗户位置在所有镜头中保持一致
- ✅ 确保光线和氛围的统一性
- ✅ 通过复用已生成的帧作为环境参考

#### 3. 场景感知过滤 ⭐⭐⭐⭐

- ✅ 根据 `scene_id` 自动过滤角色外观
- ✅ 只使用当前场景适用的服装/造型
- ✅ 支持角色在不同场景的外观变化（如 John 在办公室穿西装，在健身房穿运动服）

#### 4. 智能选择 ⭐⭐⭐⭐

- ✅ 根据镜头需求（正面/侧面/背面）选择最合适的视角
- ✅ 优先选择构图相似的参考图
- ✅ 优先选择时间上更接近的参考图

#### 5. 提示词生成 ⭐⭐⭐⭐

- ✅ 为每张参考图分配明确的索引（Image 0, Image 1...）
- ✅ 生成详细的引用说明（"reference Image 0 for character appearance"）
- ✅ 注入场景上下文（location, time_of_day）增强环境一致性

---

## 📊 完整数据流图

```
剧本 (Script)
  ↓
┌─────────────────────────────────────────┐
│ 阶段 0: ScenePlanner                    │
│ 输出: scenes.json (scene_id=0)          │
└─────────────────────────────────────────┘
  ↓                    ↓
  ↓         ┌─────────────────────────────────────────┐
  ↓         │ 阶段 1: CharacterExtractor              │
  ↓         │ 输入: scenes (使用统一的 scene_id)      │
  ↓         │ 输出: characters.json                   │
  ↓         │       (appearance_0 → scene_ids=[0])    │
  ↓         └─────────────────────────────────────────┘
  ↓                    ↓
  ↓         ┌─────────────────────────────────────────┐
  ↓         │ 阶段 2: CharacterPortraitsGenerator     │
  ↓         │ 输出: 角色肖像图片                      │
  ↓         │       0_John/appearance_0/*.png         │
  ↓         │       1_Wang/appearance_0/*.png         │
  ↓         └─────────────────────────────────────────┘
  ↓                    ↓
  ↓         ┌─────────────────────────────────────────┐
  ↓         │ 阶段 3-4: StoryboardArtist              │
  ↓         │ 输入: scenes (使用统一的 scene_id)      │
  ↓         │ 输出: storyboard.json                   │
  ↓         │       (每个镜头 scene_id=0)             │
  ↓         └─────────────────────────────────────────┘
  ↓                    ↓
  └────────────────────┴──→ 阶段 7: 生成帧和视频
                            ↓
              ┌──────────────────────────────────────┐
              │ 对每一帧调用 ReferenceImageSelector  │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ Step 1: 场景上下文构建               │
              │ (location, time_of_day, description) │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ Step 2: 场景外观过滤                 │
              │ (根据 scene_id 过滤角色外观)         │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ Step 3: 智能选择参考图（最多 8 张）  │
              │ (考虑角色、环境、构图、时间)         │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ Step 4: 生成详细提示词               │
              │ (明确引用每张参考图的用途)           │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ ImageGenerator: 生成 3 张候选图      │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ BestImageSelector: 选择最佳 1 张     │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ 保存为 first_frame.png / last_frame  │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ VideoGenerator: 基于关键帧生成视频   │
              └──────────────────────────────────────┘
                            ↓
              ┌──────────────────────────────────────┐
              │ 阶段 8: 时间线渲染                   │
              │ 输出: final_video.mp4                │
              └──────────────────────────────────────┘
```

---

## 💡 关键设计亮点

### 1. 统一场景规划系统

- ✅ **ScenePlanner 前置规划**，确保所有 Agent 使用相同的 `scene_id`
- ✅ 解决了之前 CharacterExtractor 和 StoryboardArtist 对场景理解不一致的问题
- ✅ 为多外观系统提供了统一的场景索引基础

### 2. 多外观系统

- ✅ 支持角色在不同场景穿不同服装
- ✅ 每个外观都标记了适用的 `scene_ids`
- ✅ ReferenceImageSelector 自动根据场景过滤外观

### 3. 场景感知的参考图选择

- ✅ 根据 `scene_id` 自动过滤角色肖像
- ✅ 只使用当前场景适用的服装/造型
- ✅ 避免了"办公室场景用健身房服装"的错误

### 4. 智能的一致性保证

- ✅ **角色一致性**：通过肖像参考保持外貌不变
- ✅ **环境一致性**：通过已生成帧保持场景不变
- ✅ **风格一致性**：统一的视觉风格贯穿全片
- ✅ **时序一致性**：首帧 → 末帧的连贯性

### 5. 分阶段缓存机制

- ✅ 每个阶段的输出都保存为文件
- ✅ 重新运行时自动跳过已完成的步骤
- ✅ 便于调试和增量生成
- ✅ 支持断点续传

---

## 🔧 ReferenceImageSelector 的优化空间

虽然当前系统已经很完善，但仍有以下优化空间：

### 1. Embedding 预筛选（高优先级）

- **当前**: 超过 8 张图时，用 LLM 文本模型粗筛
- **优化**: 使用 Embedding 相似度预筛选，更快更便宜

### 2. 参考图缓存（中优先级）

- **当前**: 每次都重新调用 LLM 选择
- **优化**: 缓存相似帧描述的选择结果

### 3. 场景参考图生成（长期优化）

- **当前**: 通过文本注入场景上下文（短期方案）
- **优化**: 为每个场景生成专门的环境参考图（长期方案）

### 4. 动态参考图数量（低优先级）

- **当前**: 固定最多选 8 张
- **优化**: 根据场景复杂度动态调整（简单场景 3-5 张，复杂场景 8-10 张）

---

## 🎓 总结

**ReferenceImageSelector 是 ViMax 系统中的"智能图像管家"**：

- 📚 **输入端**：收集所有可用的参考图（角色肖像 + 已生成帧）
- 🧠 **处理端**：智能分析和选择最相关的参考图，生成详细提示词
- 🎨 **输出端**：为 ImageGenerator 提供精选参考图和引导提示

它通过以下机制确保视频质量：

1. ✅ 场景外观过滤（基于 `scene_id`）
2. ✅ 多模态智能选择（基于 LLM 视觉理解）
3. ✅ 详细提示词生成（明确引用每张图）
4. ✅ 提示词验证和修复（确保正确引用）

**最终效果**：生成的视频在角色外貌、场景环境、视觉风格上保持高度一致性，达到专业影视制作的水准！🎬✨
