# 分镜级别交互模式实现文档

## 概述

本文档描述了在 `Script2VideoPipeline` 中实现的分镜级别交互模式，允许用户在每个分镜视频生成后进行审查和确认。

## 功能特性

### 1. 交互式视频生成流程

当 `interactive_mode=True` 时，系统会：

- **顺序生成**每个分镜的视频（而非并发）
- 每个分镜生成完成后**暂停**并等待用户确认
- 显示分镜的详细信息（场景 ID、镜头尺寸、角度、描述等）
- 提供三个选项：
  - `[c]` 继续 - 确认当前分镜，生成下一个
  - `[r]` 重试 - 删除当前视频文件并重新生成
  - `[q]` 退出 - 停止整个生成流程

### 2. 用户交互界面

```
================================================================================
📋 分镜视频生成 - 第 1/10 个
================================================================================

🎬 分镜 #0 已生成完成

📝 分镜描述:
  场景: 0
  镜头尺寸: medium
  镜头角度: eye_level

  首帧描述: A group of students are practicing basketball...
  运动描述: The camera slowly pans across the gym...

📁 视频路径: .working_dir/script2video/shots/0/video.mp4

================================================================================

请选择操作:
  [c] 继续下一步
  [r] 重新生成
  [q] 退出程序
>
```

## 实现细节

### 1. Pipeline 修改

#### `Script2VideoPipeline.__init__()`

添加了 `interactive_mode` 参数：

```python
def __init__(
    self,
    chat_model: str,
    image_generator,
    video_generator,
    working_dir: str,
    max_shots: int | None = None,
    interactive_mode: bool = False,  # 新增参数
):
    # ...
    self.interactive_mode = interactive_mode
```

#### `wait_for_user_confirmation()` 方法

新增方法处理用户交互：

```python
def wait_for_user_confirmation(self, stage_name: str, display_content: str = "") -> str:
    """
    等待用户确认后继续

    Args:
        stage_name: 当前阶段名称
        display_content: 要显示给用户的内容

    Returns:
        用户选择 ('c' 继续, 'r' 重试, 'q' 退出)
    """
    if not self.interactive_mode:
        return "c"

    # 显示信息并获取用户输入
    # ...
```

#### 视频生成流程修改

在 `__call__()` 方法中，将视频生成部分改为：

```python
# 视频生成部分 - 根据 interactive_mode 决定是否顺序生成并交互
if self.interactive_mode:
    # 交互模式：顺序生成每个分镜视频，并等待用户确认
    for shot_description in shot_descriptions:
        while True:
            # 生成单个分镜视频
            await self.generate_video_for_single_shot(
                shot_description=shot_description,
            )

            # 显示分镜信息并等待用户确认
            choice = self.wait_for_user_confirmation(...)

            if choice == 'c':
                break  # 继续下一个分镜
            elif choice == 'r':
                # 删除视频文件并重新生成
                os.remove(video_path)
            elif choice == 'q':
                raise KeyboardInterrupt("用户主动退出")
else:
    # 非交互模式：并发生成所有视频（保持原有性能）
    video_tasks = [...]
    await asyncio.gather(*video_tasks)
```

### 2. 配置文件支持

#### `configs/script2video.yaml`

添加了 `interactive_mode` 配置项：

```yaml
# Interactive mode: require user confirmation after each shot video generation
interactive_mode: false
```

#### `init_from_config()` 方法

从配置文件读取并传递参数：

```python
interactive_mode = config.get("interactive_mode", False)

return cls(
    # ...
    interactive_mode=interactive_mode,
)
```

### 3. Pipeline 集成

#### `Idea2VideoPipeline` 集成

在场景视频生成时传递 `interactive_mode`：

```python
script2video_pipeline = Script2VideoPipeline(
    chat_model=self.chat_model,
    image_generator=self.image_generator,
    video_generator=self.video_generator,
    working_dir=scene_working_dir,
    interactive_mode=self.interactive_mode,  # 传递交互模式
)
```

## 使用方法

### 方法 1: 通过配置文件启用

编辑 `configs/script2video.yaml`：

```yaml
interactive_mode: true
```

然后正常运行：

```bash
python main_script2video.py
```

### 方法 2: 通过 `main_idea2video.py` 启用

`Idea2VideoPipeline` 的交互模式会自动传递给 `Script2VideoPipeline`：

```python
# main_idea2video.py
interactive_mode = True  # 这会同时启用场景级和分镜级交互
```

### 方法 3: 代码中直接启用

```python
pipeline = Script2VideoPipeline(
    chat_model=chat_model,
    image_generator=image_generator,
    video_generator=video_generator,
    working_dir=working_dir,
    interactive_mode=True,  # 直接启用
)
```

## 工作流程

### 完整的交互式生成流程

1. **帧生成阶段**（并发执行，无交互）

   - 所有分镜的首帧和末帧并发生成
   - 利用已有缓存避免重复生成

2. **视频生成阶段**（顺序执行，有交互）

   - 按分镜顺序逐个生成视频
   - 每个视频生成后暂停并显示信息
   - 用户可以：
     - 确认并继续下一个
     - 重新生成当前分镜（会删除视频文件）
     - 退出整个流程

3. **最终合成阶段**（自动执行）
   - 所有分镜确认后，自动合成最终视频

## 性能考虑

### 交互模式 vs 批量模式

| 模式         | 帧生成 | 视频生成 | 用户交互       | 适用场景               |
| ------------ | ------ | -------- | -------------- | ---------------------- |
| **交互模式** | 并发   | 顺序     | 每个分镜后暂停 | 质量优先，需要精细控制 |
| **批量模式** | 并发   | 并发     | 无             | 性能优先，批量生产     |

### 优化策略

1. **帧生成保持并发**

   - 帧生成速度较快且相对稳定
   - 并发执行可显著提升效率
   - P1/P2 优化确保帧之间的一致性

2. **视频生成顺序执行**（仅交互模式）

   - 视频生成耗时较长（每个数分钟）
   - 顺序执行允许及时发现问题
   - 避免浪费资源生成不满意的后续视频

3. **缓存机制**
   - 所有已生成的文件都会被缓存
   - 重试时只需重新生成视频文件
   - 帧文件保持不变，节省时间

## 错误处理

### 用户退出处理

当用户选择 `[q]` 退出时：

- 抛出 `KeyboardInterrupt` 异常
- 已生成的分镜视频文件保留
- 可以稍后继续（从下一个分镜开始）

### 重试机制

当用户选择 `[r]` 重试时：

- 删除当前分镜的视频文件
- 清除相关事件状态（如果有）
- 重新调用 `generate_video_for_single_shot()`
- 帧文件保持不变（不会重新生成）

## 与场景级交互模式的关系

| 交互级别   | Pipeline             | 触发时机                     | 可重试内容          |
| ---------- | -------------------- | ---------------------------- | ------------------- |
| **场景级** | Idea2VideoPipeline   | 每个场景的所有分镜生成完成后 | 整个场景的分镜+视频 |
| **分镜级** | Script2VideoPipeline | 每个分镜视频生成后           | 单个分镜的视频      |

### 组合使用

当两者都启用时（`main_idea2video.py` 中 `interactive_mode=True`）：

1. 场景 1 的所有**帧**生成完成
2. **分镜 1**视频生成 → 用户确认
3. **分镜 2**视频生成 → 用户确认
4. ...
5. **分镜 N**视频生成 → 用户确认
6. 场景 1 合成完成 → **场景级**用户确认
7. 重复步骤 1-6 处理场景 2、场景 3...

## 示例输出

### 交互模式运行示例

```
🎬 Starting video generation for shot 0...
☑️ Generated video for shot 0, saved to .working_dir/script2video/shots/0/video.mp4.

================================================================================
📋 分镜视频生成 - 第 1/10 个
================================================================================

🎬 分镜 #0 已生成完成

📝 分镜描述:
  场景: 0
  镜头尺寸: medium
  镜头角度: eye_level

  首帧描述: A group of students are practicing basketball in the gym...
  运动描述: The camera slowly pans to show the crowd cheering...

📁 视频路径: .working_dir/script2video/shots/0/video.mp4

================================================================================

请选择操作:
  [c] 继续下一步
  [r] 重新生成
  [q] 退出程序
> c

✅ 分镜 #0 已确认，继续生成下一个分镜...

🎬 Starting video generation for shot 1...
☑️ Generated video for shot 1, saved to .working_dir/script2video/shots/1/video.mp4.

================================================================================
📋 分镜视频生成 - 第 2/10 个
================================================================================
...
```

## 未来改进方向

1. **预览功能**

   - 在终端中显示视频缩略图
   - 集成视频播放器自动预览

2. **批量操作**

   - 支持 `[ca]` 确认所有剩余分镜
   - 支持 `[ra]` 重新生成所有剩余分镜

3. **编辑功能**

   - 允许用户修改分镜描述后重新生成
   - 调整视频参数（时长、风格等）

4. **智能推荐**
   - 基于前面的确认模式，建议后续分镜的参数
   - 检测质量异常并提示用户

## 总结

分镜级别交互模式为用户提供了更精细的质量控制能力：

- ✅ **质量保证**: 每个分镜都经过审核
- ✅ **资源节约**: 及时发现问题，避免浪费
- ✅ **灵活控制**: 可随时重试或退出
- ✅ **向后兼容**: 不影响批量模式的性能
- ✅ **双层交互**: 与场景级交互模式完美配合

这使得 ViMax 系统更加适合高质量、精细化的视频生产场景。
