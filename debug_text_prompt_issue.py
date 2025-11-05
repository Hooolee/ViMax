"""
诊断脚本：为什么 text_prompt 会是 None
"""
import json

# 读取实际的输出
with open('.working_dir/idea2video/detective_mystery/scene_0/shots/1/first_frame_selector_output.json', 'r') as f:
    data = json.load(f)

print("=" * 80)
print("📋 分析 text_prompt 为 None 的原因")
print("=" * 80)

print("\n1️⃣ 实际保存的数据：")
print(f"   ref_image_indices count: {len(data['reference_image_path_and_text_pairs'])}")
print(f"   text_prompt value: {repr(data['text_prompt'])}")
print(f"   text_prompt type: {type(data['text_prompt'])}")

print("\n2️⃣ 参考图信息：")
for i, (path, desc) in enumerate(data['reference_image_path_and_text_pairs']):
    print(f"   Image {i}: {path.split('/')[-1]}")
    print(f"             {desc[:80]}...")

print("\n3️⃣ 问题分析：")
if data['text_prompt'] is None:
    print("   ❌ text_prompt 确实是 None (null)")
    print("\n   可能原因：")
    print("   A. AI 模型输出了 null 而不是有效字符串")
    print("   B. 模型没有理解需要生成 text_prompt")
    print("   C. 输出解析失败，但没有抛出异常")
    print("   D. 某个特殊情况下代码逻辑设置为 None")
    
print("\n4️⃣ 影响：")
print("   在 pipeline 中拼接 prompt 时：")
prompt_parts = []
for i, (path, desc) in enumerate(data['reference_image_path_and_text_pairs']):
    prompt_parts.append(f"Image {i}: {desc[:50]}...")
prefix = "\n".join(prompt_parts)
final_prompt = f"{prefix}\n{data['text_prompt']}"
print(f"   最终 prompt (前200字符)：")
print(f"   {repr(final_prompt[:200])}")
print("\n   ⚠️  注意 'None' 变成了字符串！图像生成器收到的是无效指令。")

print("\n5️⃣ 解决方案：")
print("   ✅ 已添加防御性检查：if prompt is None → 使用帧描述")
print("   ✅ 在 _validate_prompt_mapping 中添加 None 处理")
print("   ✅ 记录警告日志以便追踪")

print("\n" + "=" * 80)
