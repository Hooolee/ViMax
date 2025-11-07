# 交互模式修改总结

## 修改内容

本次修改为 `main_idea2video.py` 添加了交互模式功能，使得在每个 agent 运行结束后，程序会暂停并等待用户确认才继续执行。

## 修改的文件

### 1. `pipelines/idea2video_pipeline.py`

**核心修改**：

- 添加 `interactive_mode` 参数（默认 `True`）
- 新增 `wait_for_user_confirmation()` 方法
- 所有主要的 agent 方法都包装在 `while True` 循环中
- 每个方法执行完成后调用 `wait_for_user_confirmation()`
- 支持三种用户选项：
  - `c`: 继续下一步
  - `r`: 重新运行当前步骤
  - `q`: 退出程序

**修改的方法**：

1. `__init__()` - 添加 `interactive_mode` 参数
2. `init_from_config()` - 支持传递 `interactive_mode`
3. `wait_for_user_confirmation()` - 新增方法
4. `develop_story()` - 添加交互和内容预览
5. `write_script_based_on_story()` - 添加交互和场景信息显示
6. `plan_scenes()` - 添加交互和场景详情显示
7. `extract_characters()` - 添加交互和角色列表显示
8. `generate_character_portraits()` - 添加交互和肖像文件显示
9. `__call__()` - 为每个场景视频生成添加交互
10. `__call__()` - 最终视频完成后添加交互

### 2. `main_idea2video.py`

**修改**：

- 添加 `interactive_mode` 配置变量（默认 `True`）
- 在初始化 pipeline 时传递 `interactive_mode` 参数

### 3. 新增文档

- `docs/INTERACTIVE_MODE_GUIDE.md` - 详细使用指南
- `test_interactive_mode.py` - 测试示例脚本

### 4. 更新日志

- `CHANGELOG.md` - 添加本次更新的记录

## 使用方法

### 启用交互模式（默认）

```python
# 在 main_idea2video.py 中
interactive_mode = True
```

运行时每个步骤会显示：

```
================================================================================
🎯 [阶段名称] 阶段已完成！
================================================================================
请选择：
  [c] 继续下一步
  [r] 重新运行当前步骤
  [q] 退出程序
================================================================================
请输入选项 (c/r/q):
```

### 禁用交互模式

```python
# 在 main_idea2video.py 中
interactive_mode = False
```

程序将自动运行所有步骤，不会暂停等待用户输入。

## 关键特性

1. **内容预览**：每个阶段完成后显示关键信息

   - 故事内容预览
   - 场景信息
   - 角色列表
   - 肖像文件路径
   - 视频文件路径

2. **重新运行功能**：选择 `r` 后会自动删除当前步骤的输出文件并重新执行

3. **安全退出**：支持 `q`、`Ctrl+C` 和 `EOF` 等多种退出方式

4. **向后兼容**：可通过 `interactive_mode=False` 完全禁用交互模式

## 测试

运行测试脚本：

```bash
# 交互模式测试
python test_interactive_mode.py

# 非交互模式测试
python test_interactive_mode.py --non-interactive
```

## 注意事项

1. 在非交互环境（如 CI/CD）中使用时，请设置 `interactive_mode=False`
2. 重新运行会删除当前步骤的所有输出文件，请谨慎使用
3. 程序支持从中断处恢复（基于文件缓存）

## 技术实现

- 使用 `while True` 循环包装每个 agent 方法
- 根据用户选择决定是 `break`（继续）、`continue`（重试）还是 `sys.exit()`（退出）
- 捕获 `EOFError` 和 `KeyboardInterrupt` 异常以实现安全退出
- 使用 `input()` 函数等待用户输入

## 文件清理逻辑

重新运行时会删除：

- 故事文件 (`story.txt`)
- 剧本文件 (`script.json`)
- 场景定义文件 (`scenes.json`)
- 角色文件 (`characters.json`)
- 角色肖像注册文件和目录 (`character_portraits_registry.json`, `character_portraits/`)
- 场景工作目录 (`scene_N/`)
