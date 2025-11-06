# ViMax 优先级 TODO（以“稳定提升成片质量（视觉层）”为目标的精简版）

优先级定义：

- P0 立即优先（最小闭环，直接提升画面稳定与连贯）
- P1 应尽快（显著加分，提升专业度与效率）
- P2 可规划（运维与创作体验增强）

—

## P0 必做（最小闭环｜直接影响画面稳定）

- [x] **分镜/镜头结构补齐"摄影参数 + 节拍/时长"** ✅

  - 字段：`shot_size`、`angle`、`camera_height`、`lens_equiv_mm`、`screen_direction`、`transition_in/out`、`beat`、`duration_sec_estimate`
  - 影响：`interfaces/shot_description.py`、`agents/storyboard_artist.py`
  - 验收：分镜输出字段齐全并通过基本校验。
  - **状态**: 已在 `interfaces/shot_description.py` 中完整定义所有字段

- [ ] 连贯性与方向性校验（180/30 度）

  - 影响：新增 `utils/continuity.py`；在 `pipelines/script2video_pipeline.py` 机位树之后触发
  - 验收：违规镜头给出编号与修正建议；不通过不生成帧。
  - **状态**: `utils/continuity.py` 已存在，但需要集成到 pipeline 中

- [x] **参考图复合提示词的严格映射与校验** ✅

  - 要求：`text_prompt` 必须显式"元素 →Image N"映射；缺失/越界时报错并重试
  - 影响：`agents/reference_image_selector.py`
  - 验收：抽检通过；日志记录未引用关键元素的告警。
  - **状态**: 已在 `reference_image_selector.py` 中实现 `_validate_prompt_mapping()` 方法

- [x] **帧/镜头多采样 + 一致性选优（关键镜头优先）** ✅

  - 策略：对首帧/末帧和关键镜头 N>1 采样，用 `BestImageSelector` 选优
  - 影响：`pipelines/script2video_pipeline.py`、`agents/best_image_selector.py`
  - 验收：保留 `selection_reason.json`；失败回退记录原因。
  - **状态**: 已实现多候选生成（默认 3 张）+ BestImageSelector 选优机制

- [ ] 机位树增强与转场策略

  - 要求：父子关系加入"轴线/视距/镜头尺寸"约束；必要时自动插入过渡镜头
  - 影响：`agents/camera_image_generator.py`
  - 验收：避免"广角 → 超长焦"直接跳变；必要处插入过渡。
  - **状态**: 基础机位树已实现，但需要增强约束逻辑

- [x] **时间线/EDL 拼接替代简单拼接** ✅
  - 输出：每镜头 `in/out`、过渡类型（切/溶/叠/音先/画先），按 EDL/JSON 合成
  - 影响：新增 `utils/timeline.py`；改造 `pipelines/script2video_pipeline.py`
  - 验收：`timeline.edl` 与 `final_video.mp4` 一致，过渡自然。
  - **状态**: `utils/timeline.py` 已存在并实现

—

## P1 应尽快（质量与效率）

- [x] **场景环境参考图生成（临时方案已完成，长期方案待实现）** ⚠️

  - 作用：为每个场景预先生成参考环境图，确保同一场景的所有镜头在背景、布局、光线等方面保持严格一致
  - ✅ **当前方案（v1.2 - P1 优化）**:
    - 在 ReferenceImageSelector 的提示词中加入场景上下文（location, time_of_day, description）
    - 动态收集同场景已完成的帧作为环境参考（最多 5 个）
    - 已在 `pipelines/script2video_pipeline.py` 中实现 `collect_completed_frames_for_scene()` 方法
  - 📋 **长期方案（待实现）**:
    1. 在 ScenePlanner 之后，为每个场景生成一个"参考环境图"
    2. 后续生成该场景的所有镜头时，强制包含这个参考图
    3. 可选：使用 ControlNet 或深度图确保空间布局一致
  - 影响：新增 `agents/scene_environment_generator.py`；改造 `pipelines/script2video_pipeline.py` 和 `agents/reference_image_selector.py`
  - 验收：同一场景的不同镜头，背景布局、装饰物、窗户位置等保持完全一致
  - 优先级：P1（临时方案已实施，长期方案待规划）

- [x] **将 ScenePlanner 前置到 Idea2Video（计划稿 → 剧作）** ✅

  - 作用：结构先行，减少后期"分镜补剧情"的被动
  - 影响：`pipelines/idea2video_pipeline.py` 接入 `agents/scene_planner.py`
  - **状态**: ✅ 已完成集成
  - **实现内容**:
    1. ✅ 在 `write_script_based_on_story()` 之后，调用 `ScenePlanner.plan_scenes()` 分析完整剧本
    2. ✅ 将场景定义传递给 `CharacterExtractor`（提取角色时使用统一 scene_id）
    3. ✅ 为每个场景调用 Script2Video 时传递对应的 `SceneDefinition`
    4. ✅ 确保整个 Idea2Video 流程中 scene_id 统一
    5. ✅ 添加场景数量验证，检测 ScenePlanner 和 Screenwriter 的输出是否匹配
    6. ✅ Script2VideoPipeline 增加 `scenes` 参数，避免重复生成场景
    7. ✅ 在 `interfaces/__init__.py` 中导出 `SceneDefinition`
    8. ✅ 确保整个 Idea2Video 流程中 scene_id 统一
    9. ✅ 添加场景数量验证，检测 ScenePlanner 和 Screenwriter 的输出是否匹配

- [ ] 走位（Blocking）文本输出

  - 输出：前/中/后景布局、起落点与路径、视线方向
  - 影响：`agents/storyboard_artist.py`、`interfaces/shot_description.py` 新增 `blocking_text`
  - **状态**: 未实现

- [ ] 服装/道具/光位/色板约束

  - 场景级字段：`wardrobe_props`、`lighting_setup`、`palette`
  - 影响：`interfaces/scene.py`、`agents/storyboard_artist.py`
  - **状态**: 未实现

- [ ] 音频流水线解耦与结构化对白字段

  - 四轨：对白/拟音/环境/音乐；恢复 `speaker/line/emotion/is_speaker_lip_visible`
  - 影响：新增 `pipelines/audio_pipeline.py`、更新 `interfaces/shot_description.py`
  - **状态**: 未实现

- [ ] 产物 manifest 与可复现 seed

  - 影响：`tools/*`、`pipelines/*` 写入/读取 `manifest.json`
  - **状态**: 未实现

- [ ] 统一重试/降级与日志分段

  - 影响：`utils/retry.py`、外部 API 适配器、选择器链路
  - **状态**: 部分实现（retry.py 存在，但需要统一化）

- [ ] 将 ScriptPlanner 前置到 Idea2Video（计划稿 → 剧作）

  - 作用：结构先行，减少后期“分镜补剧情”的被动
  - 影响：`pipelines/idea2video_pipeline.py` 接入 `agents/script_planner.py`

- [ ] 走位（Blocking）文本输出

  - 输出：前/中/后景布局、起落点与路径、视线方向
  - 影响：`agents/storyboard_artist.py`、`interfaces/shot_description.py` 新增 `blocking_text`

- [ ] 服装/道具/光位/色板约束

  - 场景级字段：`wardrobe_props`、`lighting_setup`、`palette`
  - 影响：`interfaces/scene.py`、`agents/storyboard_artist.py`

- [ ] 音频流水线解耦与结构化对白字段

  - 四轨：对白/拟音/环境/音乐；恢复 `speaker/line/emotion/is_speaker_lip_visible`
  - 影响：新增 `pipelines/audio_pipeline.py`、更新 `interfaces/shot_description.py`

- [ ] 产物 manifest 与可复现 seed

  - 影响：`tools/*`、`pipelines/*` 写入/读取 `manifest.json`

- [ ] 统一重试/降级与日志分段
  - 影响：`utils/retry.py`、外部 API 适配器、选择器链路

—

## P2 可规划（运维与体验）

- [ ] 秘钥管理与 `.env.example`
  - **状态**: 未实现
- [ ] 用户需求结构化解析（风格/镜头密度/景深倾向等）
  - **状态**: 未实现
- [ ] 审片包导出（提案 PDF：梗概/角色圣经/分镜缩略/关键帧/色板/音乐参考）
  - **状态**: 未实现
- [ ] 监控与可观测性（结构化日志 + 指标）
  - **状态**: 未实现

—

## 已完成的重要优化 (v1.1 - v1.2) 🎉

### v1.1: 统一场景规划系统 ✅

- [x] **ScenePlanner Agent** - 前置场景规划，统一 scene_id
- [x] **场景定义传播** - CharacterExtractor 和 StoryboardArtist 接收统一场景定义
- [x] **多外观系统** - CharacterAppearance 支持 scene_ids 映射
- [x] **场景感知过滤** - ReferenceImageSelector 根据 scene_id 自动过滤角色外观
- [x] **场景上下文注入** - 在提示词中注入场景环境信息（临时方案）
- [x] **🆕 Idea2Video 集成** - ScenePlanner 已集成到 Idea2Video pipeline，确保全流程 scene_id 统一

### v1.2: 一致性优化系统 ✅

- [x] **P1 优化: 场景环境参考帧收集** - 动态收集同场景已完成帧作为环境参考
- [x] **P2 优化: 相机时序控制** - 确保第一个镜头末帧优先完成
- [x] **P3 优化: 场景定义验证** - 生成帧前验证 scene_id 存在
- [x] **P4 优化: 视频生成容错** - 10 分钟超时 + 文件验证 + 详细错误日志
- [x] **P5 优化: BestImageSelector 环境权重** - 环境一致性权重提升至 40%

—

## 里程碑（建议）

- **M1（P0 全量）**: ⚠️ 部分完成

  - ✅ 参数化：分镜字段完整
  - ❌ 校验：180/30 度规则待集成
  - ✅ 选优：多采样 + BestImageSelector
  - ✅ 时间线：timeline.py 已实现
  - **完成度**: 75% (3/4)

- **M2（P0+P1 主要项）**: ⏳ 进行中

  - ✅ 场景环境一致性（临时方案）
  - ✅ ScenePlanner 集成到 Idea2Video
  - ❌ 走位/服化道/光色约束
  - ❌ 结构化音频
  - **完成度**: 50% (2/4)
  - **完成度**: 33% (1/3)

- **M3（P2）**: ❌ 未开始
  - 运维与体验完善
  - 交付审片包与可观测体系
  - **完成度**: 0%
