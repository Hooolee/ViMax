# 风格一致性控制工作流程

本文档详细说明 ViMax 如何在整个视频生成流程中保持视觉风格的一致性。

## 📋 目录

- [概述](#概述)
- [核心问题](#核心问题)
- [完整工作流程](#完整工作流程)
- [关键组件](#关键组件)
- [风格控制机制](#风格控制机制)
- [问题诊断与修复](#问题诊断与修复)

---

## 概述

**问题背景**：AI 图像生成模型的每次生成都是独立的，如果不加控制，会导致：
- 同一角色在不同镜头中外貌不一致
- 场景风格突变（如动漫风格变成真人风格）
- 视觉连续性断裂

**解决方案**：通过 `ReferenceImageSelector` 和全局 `style` 参数，在每一帧生成时：
1. 选择之前生成的相关参考图
2. 生成包含明确引用和风格指示的 prompt
3. 确保图像生成器理解并遵循风格要求

---

## 核心问题

### 问题 1: 角色外貌不一致

**现象**：
```
镜头1: 江辰 - 短发、锐利眼神、黑色外套
镜头2: 江辰 - 长发、温和表情、棕色外套 ❌
```

**原因**：图像生成器不知道之前生成的江辰长什么样。

**解决**：使用角色肖像作为参考图，在 prompt 中明确引用。

### 问题 2: 视觉风格突变

**现象**：
```
镜头1: 动漫风格（Detective Conan Style）
镜头2: 真人照片风格 ❌
```

**原因**：
1. `style` 参数没有传递到图像生成环节
2. AI 模型生成的 prompt 中缺少风格信息
3. 参考图虽然选择了，但没有指示如何使用

**解决**：在所有图像生成环节强制包含 `style` 参数。

### 问题 3: `text_prompt` 为 `None`

**现象**：
```json
{
  "ref_image_indices": [0, 1],  // ✓ 选择了参考图
  "text_prompt": null            // ❌ 但没有生成 prompt
}
```

**影响**：
```python
# Pipeline 拼接 prompt
prompt = f"Image 0: 江辰侧面\nImage 1: 博物馆\n{None}"
# 结果: "Image 0: ...\nImage 1: ...\nNone"
# 图像生成器收到无效指令，随意生成
```

**解决**：当检测到 `None` 时，调用 AI 重新生成 prompt（包含 style）。

---

## 完整工作流程

### 阶段 1: 初始化

```
用户输入:
├─ idea: 故事创意
├─ user_requirement: 需求描述
└─ style: "Realistic Anime, Detective Conan Style" ← 关键！
         ↓
Pipeline 初始化:
└─ self.style = style  # 保存到实例变量
```

### 阶段 2: 角色肖像生成

```
CharacterPortraitsGenerator.generate_front_portrait(character, style)
                                                              ^^^^^
                                                        传入 style 参数
         ↓
生成角色肖像:
├─ 江辰正面肖像.png（动漫风格）✓
├─ 江辰侧面肖像.png（动漫风格）✓
└─ 江辰背面肖像.png（动漫风格）✓
```

**代码位置**：
- `pipelines/script2video_pipeline.py:generate_portraits_for_single_character()`
- `agents/character_portraits_generator.py:generate_front_portrait()`

### 阶段 3: 第一个镜头（建立场景）

```
┌─────────────────────────────────────────────────────┐
│ 镜头 0: 博物馆大厅全景                                 │
├─────────────────────────────────────────────────────┤
│ 输入:                                                │
│ - frame_description: "俯视博物馆大厅，展柜破碎..."    │
│ - available_images: [] (第一个镜头，没有参考图)        │
│ - style: "Realistic Anime, Detective Conan Style"   │
└─────────────────────────────────────────────────────┘
         ↓
ReferenceImageSelector.select_reference_images_and_generate_prompt(
    available_image_path_and_text_pairs=[],
    frame_description=desc,
    style=style  ← 传入 style
)
         ↓
┌─────────────────────────────────────────────────────┐
│ AI 模型处理:                                          │
│ 1. 选择参考图: [] (没有可选的)                        │
│ 2. 生成 prompt:                                      │
│    "Generate an image based on:                     │
│     俯视博物馆大厅，展柜破碎...                        │
│     Style: Realistic Anime, Detective Conan Style"  │
└─────────────────────────────────────────────────────┘
         ↓
Image Generator
         ↓
✅ 第一帧图像（动漫风格）
```

### 阶段 4: 后续镜头（保持一致性）

```
┌─────────────────────────────────────────────────────┐
│ 镜头 1: 江辰走近展柜                                   │
├─────────────────────────────────────────────────────┤
│ 输入:                                                │
│ - frame_description: "江辰侧面走近展柜，神情专注"      │
│ - available_images:                                 │
│   ├─ 江辰正面肖像.png                                 │
│   ├─ 江辰侧面肖像.png                                 │
│   ├─ 江辰背面肖像.png                                 │
│   └─ 镜头0_第一帧.png                                 │
│ - style: "Realistic Anime, Detective Conan Style"   │
└─────────────────────────────────────────────────────┘
         ↓
ReferenceImageSelector 工作流:
         ↓
┌─────────────────────────────────────────────────────┐
│ 步骤 1: 选择参考图                                     │
│ AI 模型分析:                                          │
│ - "需要江辰侧面... 选择侧面肖像"                       │
│ - "需要博物馆背景... 选择镜头0的图"                    │
│                                                      │
│ 输出:                                                │
│ ref_image_indices: [1, 3]                           │
│   ├─ Image 0: 江辰侧面肖像                            │
│   └─ Image 1: 镜头0的博物馆场景                       │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 步骤 2: 生成 text_prompt                              │
│                                                      │
│ 理想情况（AI 正常返回）:                              │
│ text_prompt: "Generate image following:             │
│   江辰 (reference Image 0 for appearance:           │
│   short hair, sharp eyes, dark coat) walking       │
│   towards display case (reference Image 1 for      │
│   environment: museum hall, broken glass).         │
│   Style: Realistic Anime, Detective Conan Style."  │
│                                                      │
│ 异常情况（AI 返回 null）:                             │
│ text_prompt: null                                   │
│         ↓                                            │
│ _validate_prompt_mapping() 检测到 None               │
│         ↓                                            │
│ 🔧 补救机制触发:                                      │
│ generate_prompt_for_selected_images(                │
│     selected_descriptions=[                         │
│         "江辰侧面肖像",                               │
│         "博物馆场景"                                  │
│     ],                                              │
│     frame_description="江辰侧面走近展柜...",          │
│     style="Realistic Anime, Detective Conan Style" │
│ )                                                   │
│         ↓                                            │
│ AI 重新生成高质量 prompt（包含 style）✓               │
└─────────────────────────────────────────────────────┘
         ↓
最终 prompt 拼接:
┌─────────────────────────────────────────────────────┐
│ Image 0: 江辰侧面肖像                                  │
│ Image 1: 博物馆大厅场景                                │
│                                                      │
│ Generate image following:                           │
│ 江辰 (reference Image 0 for appearance...)          │
│ towards display case (reference Image 1...)        │
│ Style: Realistic Anime, Detective Conan Style.     │
└─────────────────────────────────────────────────────┘
         ↓
Image Generator
         ↓
✅ 新一帧图像（动漫风格，江辰外貌一致）
```

---

## 关键组件

### 1. ReferenceImageSelector

**文件位置**：`agents/reference_image_selector.py`

**职责**：
- 从可用图片库中选择最相关的参考图
- 生成包含明确引用和风格指示的 text_prompt

**核心方法**：

#### `select_reference_images_and_generate_prompt()`

```python
async def select_reference_images_and_generate_prompt(
    self,
    available_image_path_and_text_pairs: List[Tuple[str, str]],
    frame_description: str,
    style: str = None,  # 风格参数
) -> Dict:
    """
    主方法：选择参考图并生成 prompt
    
    Returns:
        {
            "reference_image_path_and_text_pairs": [...],
            "text_prompt": "..."  # 包含 style
        }
    """
```

**工作流程**：
1. **预筛选**（如果参考图 ≥ 8张）：用文本模型快速筛选
2. **精选**：用多模态模型查看实际图片内容
3. **生成 prompt**：AI 生成包含明确引用的文本
4. **验证修复**：调用 `_validate_prompt_mapping()` 检查和修复

#### `generate_prompt_for_selected_images()`

```python
async def generate_prompt_for_selected_images(
    self,
    selected_image_descriptions: List[str],  # 已选图片描述
    frame_description: str,                   # 目标帧描述
    style: str = None,                        # 风格参数
) -> str:
    """
    补救方法：当主流程未生成 prompt 时，专门调用 AI 生成
    
    特点：
    - 不重新选图（图已经选好）
    - 只生成 prompt
    - 强制包含 style 信息
    """
```

**System Prompt 关键部分**：
```
[Requirements]
5. **If a visual style is specified, MUST include it in the prompt 
   to maintain consistency**

[Example Output]
"Generate an image following this description:
...
Style: Realistic Anime, Detective Conan Style."
```

#### `_validate_prompt_mapping()`

```python
async def _validate_prompt_mapping(
    self,
    text_prompt: str,
    ref_count: int,
    frame_description: str,
    selected_pairs: List[Tuple[str, str]],
    style: str = None,  # 风格参数
) -> str:
    """
    验证和修复 prompt
    
    检查项：
    1. prompt 是否为 None 或空
    2. 是否包含 "Image N" 引用
    3. 引用的索引是否在有效范围内
    4. 角色元素是否都有引用
    
    修复策略：
    - 如果 None → 调用 generate_prompt_for_selected_images()
    - 如果缺少引用 → 自动添加引用
    - 始终确保包含 style 信息
    """
```

### 2. Script2VideoPipeline

**文件位置**：`pipelines/script2video_pipeline.py`

**职责**：
- 协调整个视频生成流程
- 维护全局 `style` 参数
- 在各个生成环节传递 style

**关键修改点**：

```python
class Script2VideoPipeline:
    def __init__(self, ..., style: str = None):
        self.style = style  # 保存 style
    
    async def __call__(self, script, user_requirement, style, ...):
        self.style = style  # 更新 style
        
        # 生成角色肖像时传入 style
        await self.generate_portraits_for_single_character(character, style)
        
        # 选择参考图和生成 prompt 时传入 style
        ff_selector_output = await self.reference_image_selector.\
            select_reference_images_and_generate_prompt(
                available_image_path_and_text_pairs=...,
                frame_description=...,
                style=self.style,  # ← 关键！
            )
```

---

## 风格控制机制

### 层级 1: 源头控制

在用户输入时明确指定风格：

```python
# main_idea2video.py
style = "Realistic Anime, Detective Conan Style"

await pipeline(idea=idea, user_requirement=req, style=style)
```

### 层级 2: 角色肖像

确保角色肖像从一开始就符合风格：

```python
# agents/character_portraits_generator.py
async def generate_front_portrait(character, style):
    prompt = f"Generate a front-view portrait of {character.name}..."
    prompt += f"\nStyle: {style}"  # ← 包含风格
```

### 层级 3: 场景生成（主流程）

AI 模型在生成 prompt 时应该自动包含 style：

```python
# System Prompt 中已有指示
"Ensure the language of all output values matches that used 
in the frame description."
```

**注意**：这一层依赖 AI 模型的理解，可能失败！

### 层级 4: 补救机制

当层级 3 失败时（prompt 为 None），强制生成包含 style 的 prompt：

```python
# agents/reference_image_selector.py
async def _validate_prompt_mapping(..., style):
    if text_prompt is None:
        # 调用补救方法，强制传入 style
        return await self.generate_prompt_for_selected_images(
            selected_descriptions=...,
            frame_description=...,
            style=style,  # ← 强制包含
        )
```

### 层级 5: 最终保险

在 pipeline 中拼接 prompt 时，再次检查：

```python
# pipelines/script2video_pipeline.py
prompt = selector_output["text_prompt"]
if prompt is None or not prompt.strip():
    logging.warning("text_prompt is None, using frame description")
    prompt = f"Generate: {frame_desc}"
    if self.style:
        prompt += f"\n\nStyle: {self.style}"  # 添加 style
```

---

## 问题诊断与修复

### 问题场景 1: 风格突变

**症状**：
```
第1帧：动漫风格 ✓
第2帧：真人风格 ❌
```

**诊断步骤**：

1. 检查是否传入了 style：
```bash
# 查看日志
grep "style" logs/pipeline.log
```

2. 检查 selector 输出：
```bash
cat .working_dir/xxx/scene_0/shots/1/first_frame_selector_output.json
```

3. 检查 text_prompt 内容：
```json
{
  "reference_image_path_and_text_pairs": [...],
  "text_prompt": "..."  // 是否包含 "Style: ..." ?
}
```

**可能原因与解决**：

| 原因 | 位置 | 解决方案 |
|------|------|----------|
| style 参数未传入 | `main_idea2video.py` | 检查是否指定了 style |
| pipeline 未保存 style | `Script2VideoPipeline.__call__()` | 添加 `self.style = style` |
| selector 未接收 style | 调用 `select_reference_images_and_generate_prompt()` | 添加 `style=self.style` 参数 |
| prompt 生成时丢失 style | `generate_prompt_for_selected_images()` | 检查 system/human prompt 是否强调 style |

### 问题场景 2: text_prompt 为 None

**症状**：
```json
{
  "text_prompt": null
}
```

**影响**：
- 参考图虽然选择了，但没有使用指南
- 最终 prompt 变成 "...\nNone"
- 风格和角色信息丢失

**自动修复流程**：

```
检测到 None
    ↓
_validate_prompt_mapping()
    ↓
调用 generate_prompt_for_selected_images()
    ↓
AI 重新生成 prompt（包含 style）
    ↓
✅ 问题解决
```

**手动检查**：

```python
# 查看日志
grep "text_prompt is None" logs/pipeline.log

# 查看是否触发了补救机制
grep "Calling AI to generate a proper prompt" logs/pipeline.log

# 查看生成的 prompt
grep "Generated prompt via fallback" logs/pipeline.log
```

### 问题场景 3: 参考图未被使用

**症状**：
- 参考图选择了（ref_image_indices 有值）
- 但生成的图像与参考图不符

**诊断**：

检查 text_prompt 是否包含明确引用：

```python
# 正确示例
"江辰 (reference Image 0 for appearance: short hair, sharp eyes)"
         ^^^^^^^^^^^^^^^^^^^
         明确引用 Image 0

# 错误示例  
"江辰走近展柜"
# 虽然选了参考图，但 prompt 里没有说如何使用
```

**解决**：

1. 检查 `_validate_prompt_mapping()` 是否工作：
```python
# 应该检测到缺少引用
indices = [int(m.group(1)) for m in re.finditer(r"\bImage\s+(\d+)\b", text_prompt)]
if not indices:
    # 应该触发修复
```

2. 改进 system prompt，强调必须包含引用：
```
**CRITICAL REQUIREMENT for text_prompt:**
You MUST explicitly reference the selected images using the format 
"Image N" (where N is the index from ref_image_indices) in your text_prompt.
```

---

## 调试技巧

### 1. 添加详细日志

```python
# 在关键点添加打印
print(f"\n{'='*80}")
print(f"🎨 Generating frame for shot {shot_idx}")
print(f"📝 Final prompt to image generator:")
print(f"{prompt}")
print(f"🖼️  Using {len(reference_image_paths)} reference images")
print(f"🎭 Style: {self.style}")
print(f"{'='*80}\n")
```

### 2. 检查中间结果

```bash
# 查看所有 selector 输出
find .working_dir -name "*selector_output.json" -exec cat {} \;

# 检查是否都有 text_prompt
find .working_dir -name "*selector_output.json" -exec grep -H "text_prompt" {} \;
```

### 3. 对比参考图和生成图

```python
# 生成图时记录使用的参考图
print(f"Reference images used:")
for i, path in enumerate(reference_image_paths):
    print(f"  Image {i}: {path}")
```

---

## 最佳实践

### 1. 风格描述要具体

❌ 不好：
```python
style = "cartoon"
```

✅ 好：
```python
style = "Realistic Anime, Detective Conan Style, detailed character design, dramatic lighting"
```

### 2. 在所有环节传递 style

确保 style 参数贯穿：
- 角色肖像生成
- 参考图选择
- Prompt 生成
- 补救机制

### 3. 验证参考图质量

确保角色肖像图：
- 风格一致
- 清晰可辨
- 角度多样（正面、侧面、背面）

### 4. 监控 text_prompt 质量

定期检查生成的 prompt：
- 是否包含 style
- 是否有明确的 Image N 引用
- 是否与帧描述匹配

---

## 总结

### 核心机制

```
风格一致性 = 源头控制 + 参考图选择 + Prompt 生成 + 补救机制
              ^^^^^      ^^^^^        ^^^^^        ^^^^^
              用户指定    保持外貌      明确引用      自动修复
```

### 关键文件

```
agents/reference_image_selector.py
├─ select_reference_images_and_generate_prompt()  # 主流程
├─ generate_prompt_for_selected_images()          # 补救方法
└─ _validate_prompt_mapping()                     # 验证修复

pipelines/script2video_pipeline.py
├─ __init__() / __call__()                        # 保存 style
├─ generate_portraits_for_single_character()      # 角色肖像
└─ 两处调用 select_reference_images_and_generate_prompt()  # 传入 style

main_idea2video.py
└─ style = "..."                                  # 用户指定
```

### 风格控制的五层防护

```
Layer 5: Pipeline 最终检查 (prompt + style)
         ↑
Layer 4: 补救机制 (generate_prompt_for_selected_images)
         ↑
Layer 3: Prompt 验证 (_validate_prompt_mapping)
         ↑
Layer 2: 参考图选择 (select_reference_images_and_generate_prompt)
         ↑
Layer 1: 源头控制 (用户指定 style)
```

只要任意一层生效，风格一致性就能得到保证！🎯
