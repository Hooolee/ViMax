# ViMax 项目架构与实现细节

本文件整理 ViMax 的整体架构、核心 Agent 职责、模块之间的串接关系、提示词（Prompt）设计与理由，以及运行配置与产物缓存策略。旨在帮助快速理解从“创意/脚本/小说输入”到“分镜→帧→镜头→成片”的端到端生成流程。

- 代码根目录：`/Users/a10763/codes/ViMax`
- 主要入口：`main_idea2video.py`、`main_script2video.py`
- 关键目录：`agents/`（智能体）、`pipelines/`（流水线）、`interfaces/`（数据结构）、`tools/`（图像/视频生成适配器）、`utils/`（通用工具）、`configs/`（运行配置）
- 工作产物目录：`.working_dir/*`（各阶段产物缓存，便于断点续跑与复用）


## 目录结构速览（关键文件）

- `agents/`
  - `screenwriter.py`（剧作）: `class Screenwriter`（agents/screenwriter.py:118）
  - `storyboard_artist.py`（分镜）: `class StoryboardArtist`（agents/storyboard_artist.py:170）
  - `camera_image_generator.py`（机位/过渡）: `class CameraImageGenerator`（agents/camera_image_generator.py:103）
  - `character_extractor.py`（角色抽取）: `class CharacterExtractor`（agents/character_extractor.py:64）
  - `character_portraits_generator.py`（角色画像）: `class CharacterPortraitsGenerator`（agents/character_portraits_generator.py:35）
  - `reference_image_selector.py`（参考图筛选+提示词生成）: `class ReferenceImageSelector`（agents/reference_image_selector.py:138）
  - `best_image_selector.py`（候选帧一致性评估）: `class BestImageSelector`（agents/best_image_selector.py:61）
  - `script_enhancer.py`（剧本润色增强）: `class ScriptEnhancer`（agents/script_enhancer.py:73）
  - `script_planner.py`（从基本创意到计划稿）: `class ScriptPlanner`（agents/script_planner.py:329）
  - （Novel 相关）`event_extractor.py`、`scene_extractor.py`、`global_information_planner.py`、`novel_compressor.py`

- `pipelines/`
  - `idea2video_pipeline.py`: `class Idea2VideoPipeline`（pipelines/idea2video_pipeline.py:14）
  - `script2video_pipeline.py`: `class Script2VideoPipeline`（pipelines/script2video_pipeline.py:17）
  - `novel2movie_pipeline.py`（草案，TODO）

- `interfaces/`（核心数据结构，Pydantic 模型）
  - `Scene`（interfaces/scene.py）
  - `ShotBriefDescription` / `ShotDescription`（interfaces/shot_description.py）
  - `CharacterInScene` / `CharacterInEvent` / `CharacterInNovel`（interfaces/character.py）
  - `Camera`（interfaces/camera.py）、`ImageOutput`（interfaces/image_output.py）、`VideoOutput`（interfaces/video_output.py）

- `tools/`（生成适配器）
  - 图像：`ImageGeneratorNanobananaGoogleAPI` 等
  - 视频：`VideoGeneratorDoubaoSeedanceOfficialAPI`、`VideoGeneratorVeoGoogleAPI` 等

- `configs/`
  - `idea2video.yaml`、`script2video.yaml`（配置模型与工作目录等，不要在仓库公开 API Key）


## 核心数据结构（interfaces/）

- `Scene`：一幕的完整信息（场景环境、角色清单、脚本文本）。
- `ShotBriefDescription`：分镜阶段的“镜头简述”（包含 `cam_idx`、`visual_desc`、`audio_desc`、`is_last`）。
- `ShotDescription`：镜头细化后的结构化信息（首帧/末帧文本、可见角色索引、`variation_type`、`motion_desc`、`audio_desc`）。
- `Character*`：在 Scene/Event/Novel 三个层面的角色标识与特征聚合。
- `Camera`：同一场景内的多机位组织与父子关系（用于模拟多机位拍摄）。
- `ImageOutput` / `VideoOutput`：统一封装保存/下载等 IO 能力。

采用 Pydantic 强类型与 `langchain` 的 `PydanticOutputParser` 来驱动模型输出结构化，保障各 Agent 之间的接口契约与可验证性。


## Agents 职责与实现要点

以下各 Agent 的 Prompt 均采用“system + human”结构，强调：
- 输出语言与输入一致（多语言场景不中断）。
- 采用明确的字段/格式约束（通过 `parser.get_format_instructions()` 注入）。
- 强调影视语言与可拍摄性，避免抽象隐喻与“摄影机指令”。


### 1) Screenwriter（剧作）
- 位置：`agents/screenwriter.py:118`
- 能力：
  - `develop_story(idea, user_requirement)`：从创意扩写成完整故事文稿（目标受众、体裁、摘要、完整叙事）。
  - `write_script_based_on_story(story, user_requirement)`：将故事改编为“按场景划分的剧本列表”（每个元素为单场景脚本）。
- 关键 Prompt 设计：
  - Story 开发：强调三幕/人物动机/节奏/可影视化描述。
  - 剧本改编：按“场景”为基本单位，要求可分镜（动作、对白、节奏清晰）。
- 设计理由：先抽象故事→再产出“按场景组织的脚本”，为后续分镜与机位设计奠定结构基础。


### 2) CharacterExtractor（角色抽取）
- 位置：`agents/character_extractor.py:64`
- 能力：从脚本文本中抽取 `CharacterInScene` 列表（是否可见、静态特征、动态特征）。
- Prompt 约束：
  - 静态特征（如五官、体型）与动态特征（服饰、配件）分离；
  - 名称一贯性与可视化表达；
  - 背景路人不单独建模。
- 设计理由：将“人物设定”显式化，作为后续画像与参考图一致性的锚点。


### 3) CharacterPortraitsGenerator（角色画像）
- 位置：`agents/character_portraits_generator.py:35`
- 能力：基于角色特征与风格生成“前/侧/后”三视图肖像，作为一致性参考。
- Prompt 模板：
  - 正面：纯白背景、正视、自然站姿；
  - 侧面/背面：基于前视图进行一致性变换。
- 设计理由：沉淀为“角色形象基准库”，供当前/后续镜头的角色一致性引用。


### 4) StoryboardArtist（分镜与镜头拆解）
- 位置：`agents/storyboard_artist.py:170`
- 能力：
  - `design_storyboard(script, characters, user_requirement)` → `List[ShotBriefDescription]`（单场景的镜头序列）。
  - `decompose_visual_description(shot_brief_desc, characters)` → `ShotDescription`（将一条视觉描述拆分为首帧/末帧/运动）。
- Prompt 要点：
  - 分镜：镜头目的明确、语言影视化、每镜头一行对白（若有），禁止跨镜互指；
  - 拆解：分别产出 `ff_desc/lf_desc/motion_desc`，并标注可见角色索引，分类 `variation_type`（small/medium/large）。
- 设计理由：分层细化，先“镜头意图与顺序”，再“帧级要素”，便于后续图像/视频生成与多机位衔接。


### 5) CameraImageGenerator（机位树构建 + 过渡）
- 位置：`agents/camera_image_generator.py:103`
- 能力：
  - `construct_camera_tree(cameras, shot_descs)`：根据镜头描述构建“机位父子树”。
  - `generate_transition_video(...)`：使用父镜头首帧与两段描述生成“转场视频”。
  - `get_new_camera_image(transition_video_path)`：从转场视频中切出“新机位参照图”。
  - `generate_first_frame(shot_desc, portraits)`：根据 `ff_desc` 与画像生成首帧。
- Prompt 关键设计：
  - 机位树：以“视野包含关系、镜头尺寸、时间邻近、单根树、首机位为根”为准则，输出父机位与依赖的父镜头索引；
  - 过渡：确保两段画面的风格一致，用父镜头首帧做参考。
- 设计理由：模拟同一场景内的多机位拍摄，保证空间/背景在镜头间的稳定与可追踪性。


### 6) ReferenceImageSelector（参考图筛选 + 条件提示词生成）
- 位置：`agents/reference_image_selector.py:138`
- 能力：在可用参考图（角色画像+已有帧）中：
  - 先“文本-only”过滤（≥8 张时降维到更相关的集合），
  - 再“多模态”精筛并生成可直接用于“图生图”的复合提示词（明确哪些元素参考哪张图片）。
  - 若多模态不可用或失败，自动回退到文本-only 流程。
- 设计理由：
  - 通过两段式筛选降低无关参考的干扰；
  - 生成严格的“指代关系清晰”的条件提示词，提升一致性与生成可控性。


### 7) BestImageSelector（候选帧一致性评估，可选）
- 位置：`agents/best_image_selector.py:61`
- 能力：给定“参考图+目标帧描述+候选生成图”，由多模态模型评估并选出最一致的结果。
- 当前 Pipeline 中未默认启用，但与 README 的“一致性评估”设想一致，便于后续集成在需要多次采样的环节。


### 8) ScriptEnhancer / ScriptPlanner（剧本增强与计划）
- 位置：`agents/script_enhancer.py:73` / `agents/script_planner.py:329`
- 能力：
  - `ScriptPlanner`：从基本创意出发，进行意图路由（narrative/motion/montage），选择对应模板产出“计划稿”（结构化输出：结构、角色、节奏）。
  - `ScriptEnhancer`：在不改变情节的前提下，强化连续性与感官细节，统一命名/术语，禁止隐喻/机位词，重复人物音色特征辅助后续语音绑定。
- 设计理由：
  - 计划稿用于前置梳理结构与语义边界；
  - 润色增强确保“可分镜、可拍摄、可绑定音视频”的脚本质量。


### 9) Novel 系列（长文改编，处于开发中）
- `novel_compressor.py`：长文压缩与块合并。
- `event_extractor.py`：按“事件链”逐步抽取（agents/event_extractor.py:79）。
- `scene_extractor.py`：RAG 辅助将事件改编为 Scene（agents/scene_extractor.py:61）。
- `global_information_planner.py`：跨场景/跨事件角色合并（agents/global_information_planner.py:140）。
- 状态：`pipelines/novel2movie_pipeline.py` 为草案，引用的 `components.*` 命名尚未与当前 `interfaces.*` 对齐（后续需统一）。


## Pipelines 串接流程

### A. Idea2Video（从创意到成片）
- 文件：`pipelines/idea2video_pipeline.py:14`
- 步骤：
  1) `Screenwriter.develop_story` 产出完整故事文本 → `.working_dir/idea2video/story.txt`
  2) `CharacterExtractor.extract_characters` 从故事抽取角色 → `characters.json`
  3) `CharacterPortraitsGenerator` 为每个角色生成“前/侧/后”画像 → `character_portraits/*`
  4) `Screenwriter.write_script_based_on_story` 将故事切分为多个“单场景脚本” → `script.json`
  5) 逐场景调用 `Script2VideoPipeline` 产出每个场景小片段，最后串联为总视频。

### B. Script2Video（从脚本到成片）
- 文件：`pipelines/script2video_pipeline.py:17`
- 步骤（单场景脚本）：
  1) 角色抽取与画像生成（可从上游复用）
  2) `StoryboardArtist.design_storyboard` → `storyboard.json`（镜头简述序列）
  3) `StoryboardArtist.decompose_visual_description` → 每镜头 `shot_description.json`
  4) 构建机位树：`CameraImageGenerator.construct_camera_tree` → `camera_tree.json`
  5) 帧生成（按机位并行）：
     - 首镜头：若有父镜头 → 生成“转场视频”并切帧得到“新机位图”；
     - 调用 `ReferenceImageSelector` 选择参考图并生成复合提示词 → 生成 `first_frame.png`；
     - 若 `variation_type` ∈ {medium, large} → 同理生成 `last_frame.png`；
     - 同一机位的后续镜头，沿用首镜头 `first_frame` 作为强参考，补齐各自 `first/last` 帧。
  6) 镜头视频：`video_generator.generate_single_video`，以 `motion_desc + \n + audio_desc` 为文本提示，配合 `first/last` 帧 → `video.mp4`
  7) 拼接所有镜头视频为场景视频 → `final_video.mp4`

- 并发与同步：
  - 使用 `asyncio` 并发调度，`asyncio.Event` 精确同步帧就绪；
  - 产物持久化，存在即跳过，支持断点续跑。


## Prompt 设计与理由（跨模块共性）

- 结构化输出：所有需要结构化结果的 Agent 均通过 `PydanticOutputParser` 注入 `format_instructions`，让大模型严格按字段产出（减少后处理复杂度）。
- 影视语言：
  - 分镜/镜头描述均强调“可拍摄性”（镜头尺寸、机位、构图、光照、空间关系），避免抽象隐喻与摄影机指令；
  - 对话在 `visual_desc` 或 `motion_desc` 中以“角色特征 + 引号对白”的格式出现，方便后续将音视频绑定。
- 一致性控制：
  - 通过“角色画像”与“已有帧”作为参考图；
  - `ReferenceImageSelector` 先文本降维、再多模态精筛并生成清晰的“指代关系提示词”；
  - 机位树约束“父包含子”的视野关系，且首机位为根，保障空间连续性；
  - `variation_type` 控制是否需要末帧与更强的运动建模。
- 失败回退与重试：
  - 所有关键调用使用 `tenacity` 重试（`utils/retry.after_func` 记录原因与次数）；
  - 多模态失败自动退化到文本-only 流程（参考图筛选）。


## 运行与配置

- 配置文件：`configs/idea2video.yaml`、`configs/script2video.yaml`
  - `chat_model.init_args`：模型、基座 URL、API Key（请勿泄露）。
  - `image_generator` / `video_generator`：适配器类路径与初始化参数（如 Google Gemini 图生图、Doubao Ark 文生视频）。
  - `working_dir`：流程产物输出位置（默认 `.working_dir/*`）。
- 入口脚本：`main_idea2video.py`、`main_script2video.py`
  - 按需填入 `idea/script`、`user_requirement`、`style`，调用相应 Pipeline。


## 产物与缓存（工作目录）

- Idea2Video 示例产物：
  - `story.txt`、`script.json`、`characters.json`、`character_portraits/*`
  - 每个场景：`scene_i/shots/{idx}/(first_frame.png|last_frame.png|video.mp4)`、`camera_tree.json` 等。
- Script2Video 直接在其 `working_dir` 下生成上述同类产物。
- 存在即跳过（idempotent），可反复运行叠代生成。


## 已知状态与后续建议

- `pipelines/novel2movie_pipeline.py` 仍为草案，路径引用尚未与 `interfaces/*` 完全对齐，后续需统一命名并逐步打通长文改编全链路。
- `BestImageSelector` 尚未在主流程中强制启用；在需要多次采样挑选最一致帧的阶段可集成以增强稳健性。
- 配置文件请勿提交真实密钥；建议使用本地环境变量注入或 `.env` 管理。
- 视频生成适配器目前默认返回 URL 并通过 `utils/video.download_video` 落盘，如需离线环境可扩展为 Bytes 直存。


---

以上为 ViMax 的架构与实现细节。如需我补充英文版架构说明或生成一张流程图（Mermaid），请告诉我。

## 流程图（Mermaid）

```mermaid
flowchart TD
  %% 顶层输入与入口
  A[输入层\n创意 / 脚本 / 小说] --> B{入口选择}
  B -->|Idea2Video| I2V[Idea2Video Pipeline]
  B -->|Script2Video| S2V[Script2Video Pipeline]

  %% Idea2Video 子流程
  subgraph G1[Idea2Video：从创意到脚本]
    I2V --> I2V1[Screenwriter.develop_story\n生成故事: story.txt]
    I2V1 --> I2V2[CharacterExtractor.extract_characters\n生成: characters.json]
    I2V2 --> I2V3[CharacterPortraitsGenerator\n生成角色画像 前/侧/后]
    I2V3 --> I2V4[Screenwriter.write_script_based_on_story\n生成脚本列表: script.json]
    I2V4 --> I2V5[逐场景调用 Script2Video]
  end

  %% Script2Video 子流程
  subgraph G2[Script2Video：从脚本到成片（单场景）]
    S2V --> S2V1[StoryboardArtist.design_storyboard\n生成分镜: storyboard.json]
    S2V1 --> S2V2[StoryboardArtist.decompose_visual_description\n拆解镜头: shot_description.json]
    S2V2 --> S2V3[CameraImageGenerator.construct_camera_tree\n构建机位树: camera_tree.json]

    %% 多机位与过渡
    S2V3 --> CTree{是否存在子机位}
    CTree -->|是| T1[生成过渡视频\nfirst->second 描述一致性]
    T1 --> T2[从过渡视频切帧\n得到新机位参考图]
    CTree -->|否| S2V4

    %% 参考图选择与帧生成
    S2V2 --> S2V4[ReferenceImageSelector\n筛选参考图 & 生成复合提示词]
    T2 --> S2V4
    S2V4 --> F1[生成首帧 first_frame.png]
    S2V4 --> F2[生成末帧 last_frame.png\n(当 variation 为 medium/large)]

    %% 镜头视频与拼接
    F1 --> V1[VideoGenerator.generate_single_video\n输入: motion_desc + audio_desc\n参考: first/last 帧]
    F2 --> V1
    V1 --> CONCAT[拼接镜头为场景\nfinal_video.mp4]
  end

  %% Idea2Video 汇总输出
  I2V5 --> OUT[汇总各场景视频并拼接\n最终视频]

  %% 说明：各阶段工件持久化在 .working_dir 下，存在即跳过，支持断点续跑
```
