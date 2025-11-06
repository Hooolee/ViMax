"""
测试一致性优化效果 - 完整流程版本
包含完整的 Pipeline 流程，只跳过视频生成

流程：
1. 场景规划
2. 角色提取  
3. 角色肖像生成
4. 分镜设计
5. 视觉描述分解
6. Camera Tree 构建
7. 帧生成（测试优化点）

测试场景：办公室场景，有环境变化（咖啡杯）
验证点：
  1. P1优化：后续镜头能看到之前镜头的环境变化
  2. P2优化：同一Camera的帧按时序生成
  3. P5优化：BestImageSelector选择环境一致的候选图
  4. 角色外貌一致性
"""

import asyncio
import os
import sys
import logging
from datetime import datetime
import yaml

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipelines.script2video_pipeline import Script2VideoPipeline
from interfaces import ShotDescription
from utils.model_init import init_chat_model_compat
from utils.config import resolve_env_vars
import importlib


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_consistency_optimization.log'),
        logging.StreamHandler()
    ]
)


# 测试脚本：办公室场景，有环境变化
TEST_SCRIPT = """
场景1：办公室 - 白天
镜头1：
John坐在办公桌前，桌面是空的。他在思考问题。
（首帧：桌面空的；末帧：John拿起桌上的咖啡杯）

镜头2：
切换到Mary的视角，她从门口走进办公室。
桌上可以看到John刚才拿起的咖啡杯。
（首帧：Mary在门口，可以看到桌上的咖啡杯）

镜头3：
回到John，他喝了一口咖啡，然后放下杯子。
（首帧：John手里拿着咖啡杯；末帧：咖啡杯回到桌上）

镜头4：
再次切换到Mary的视角，她走近John。
桌上的咖啡杯应该在那里。
（首帧：Mary走近，桌上有咖啡杯）
"""


async def init_pipeline_for_frame_test(output_subdir: str):
    """
    初始化 Pipeline，但不加载视频生成器（避免需要 API 凭证）
    只用于测试帧生成
    """
    # 读取配置
    config_path = "configs/script2video.yaml"
    with open(config_path, "r") as f:
        config = resolve_env_vars(yaml.safe_load(f))
    
    # 初始化聊天模型
    chat_model_args = config["chat_model"]["init_args"]
    chat_model = init_chat_model_compat(**chat_model_args)
    
    # 初始化图像生成器
    image_generator_cls_module, image_generator_cls_name = config["image_generator"]["class_path"].rsplit(".", 1)
    image_generator_cls = getattr(importlib.import_module(image_generator_cls_module), image_generator_cls_name)
    image_generator_args = config["image_generator"]["init_args"]
    image_generator = image_generator_cls(**image_generator_args)
    
    # 创建一个模拟的视频生成器（不会真正使用）
    class MockVideoGenerator:
        async def generate_single_video(self, *args, **kwargs):
            """返回一个假的视频输出，避免中断测试流程"""
            from interfaces.video_output import VideoOutput
            import io
            
            # 创建一个空的视频输出对象
            print("⚠️  跳过视频生成（测试模式）")
            
            # 返回一个模拟的 VideoOutput
            # 注意：这只是为了测试，不会真正生成视频文件
            class MockVideoOutput:
                def __init__(self):
                    self.data = b''  # 空数据
                
                def save(self, path):
                    """保存一个占位符文件"""
                    import os
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    # 创建一个空文件作为占位符
                    with open(path, 'wb') as f:
                        f.write(b'MOCK_VIDEO')
                    print(f"  → 创建占位符视频文件: {path}")
            
            return MockVideoOutput()
    
    # 创建模拟的相机图像生成器,避免尝试打开假视频文件
    class MockCameraImageGenerator:
        async def generate_transition_video(self, *args, **kwargs):
            """返回一个假的视频输出，避免真正生成转场视频"""
            print("⚠️  跳过转场视频生成（测试模式）")
            # 返回和 MockVideoGenerator 一样的输出
            class MockVideoOutput:
                def __init__(self):
                    self.data = b''
                
                def save(self, path):
                    import os
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'wb') as f:
                        f.write(b'MOCK_VIDEO')
                    print(f"  → 创建占位符转场视频: {path}")
            
            return MockVideoOutput()
        
        def get_new_camera_image(self, transition_video_path):
            """返回一个假的图像，避免尝试打开视频文件"""
            from PIL import Image
            print(f"⚠️  跳过从视频提取相机图像（测试模式）: {transition_video_path}")
            # 返回一个简单的占位图像
            return Image.new('RGB', (512, 512), color='gray')
    
    video_generator = MockVideoGenerator()
    
    # 可选的镜头限制
    max_shots = None
    cfg_max_shots = config.get("max_shots")
    if isinstance(cfg_max_shots, int) and cfg_max_shots > 0:
        max_shots = cfg_max_shots
    
    # 设置工作目录
    base_working_dir = config["working_dir"]
    working_dir = os.path.join(base_working_dir, output_subdir)
    
    # 确保工作目录存在
    os.makedirs(working_dir, exist_ok=True)
    
    # 创建 Pipeline 实例
    pipeline = Script2VideoPipeline(
        chat_model=chat_model,
        image_generator=image_generator,
        video_generator=video_generator,
        working_dir=working_dir,
        max_shots=max_shots,
    )
    
    # 替换 camera_image_generator 为 Mock 版本
    pipeline.camera_image_generator = MockCameraImageGenerator()
    
    return pipeline


async def test_frame_generation_only():
    """
    只测试帧生成，不生成视频
    包含完整流程：场景规划 → 角色提取 → 角色肖像 → 分镜 → 帧生成
    支持断点续传：如果之前已生成部分内容，会自动加载并跳过
    """
    import json
    from interfaces.scene import SceneDefinition
    from interfaces.character import CharacterInScene
    from interfaces.shot_description import ShotBriefDescription, ShotDescription
    
    print("="*80)
    print("🧪 开始测试一致性优化 - 完整流程（不含视频）")
    print("="*80)
    
    # 使用固定的测试输出目录，方便断点续传
    test_output_dir = "test_outputs/consistency_test_latest"
    os.makedirs(test_output_dir, exist_ok=True)
    
    print(f"\n📁 测试输出目录: {test_output_dir}")
    print(f"💡 提示: 使用固定目录以支持断点续传\n")
    
    try:
        # 初始化 Pipeline（手动方式，避免加载视频生成器）
        print("🔧 初始化 Pipeline（仅帧生成模式）...")
        pipeline = await init_pipeline_for_frame_test(
            output_subdir="consistency_test_latest"
        )
        
        print("✅ Pipeline 初始化成功\n")
        
        # 定义测试脚本和风格
        style = "realistic, cinematic, office environment"
        
        print("="*80)
        print("📝 步骤 1: 场景规划")
        print("="*80)
        scenes_path = os.path.join(pipeline.working_dir, "scenes.json")
        if os.path.exists(scenes_path):
            print("🚀 发现已有场景文件，加载中...")
            try:
                with open(scenes_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        print("⚠️ 场景文件为空，将重新生成")
                        scenes = None
                    else:
                        scenes = [SceneDefinition.model_validate(s) for s in json.loads(content)]
                        print(f"✅ 加载了 {len(scenes)} 个场景（跳过生成）\n")
            except json.JSONDecodeError as e:
                print(f"⚠️ 场景文件解析失败: {e}，将重新生成")
                scenes = None
        else:
            scenes = await pipeline.plan_scenes(script=TEST_SCRIPT)
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump([s.model_dump() for s in scenes], f, ensure_ascii=False, indent=4)
            print(f"✅ 规划了 {len(scenes)} 个场景\n")
        
        pipeline.scenes = scenes
        pipeline.scenes_dict = {scene.scene_id: scene for scene in scenes}
        
        print("="*80)
        print("👥 步骤 2: 角色提取")
        print("="*80)
        characters_path = os.path.join(pipeline.working_dir, "characters.json")
        if os.path.exists(characters_path):
            print("🚀 发现已有角色文件，加载中...")
            try:
                with open(characters_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        print("⚠️ 角色文件为空，将重新生成")
                        characters = None
                    else:
                        characters = [CharacterInScene.model_validate(c) for c in json.loads(content)]
                        print(f"✅ 加载了 {len(characters)} 个角色（跳过生成）\n")
            except json.JSONDecodeError as e:
                print(f"⚠️ 角色文件解析失败: {e}，将重新生成")
                characters = None
        else:
            characters = await pipeline.extract_characters(script=TEST_SCRIPT, scenes=scenes)
            with open(characters_path, 'w', encoding='utf-8') as f:
                json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=4)
            print(f"✅ 提取了 {len(characters)} 个角色\n")
        
        for char in characters:
            print(f"  - {char.identifier_in_scene}: {char.static_features}")
            if char.appearances:
                print(f"    外观数量: {len(char.appearances)}")
        
        print("\n" + "="*80)
        print("🎨 步骤 3: 生成角色肖像")
        print("="*80)
        character_portraits_path = os.path.join(pipeline.working_dir, "character_portraits_registry.json")
        if os.path.exists(character_portraits_path):
            print("🚀 发现已有角色肖像文件，加载中...")
            with open(character_portraits_path, 'r', encoding='utf-8') as f:
                character_portraits_registry = json.load(f)
            print(f"✅ 加载了 {len(character_portraits_registry)} 个角色的肖像（跳过生成）\n")
        else:
            character_portraits_registry = await pipeline.generate_character_portraits(
                characters=characters,
                character_portraits_registry=None,
                style=style,
            )
            with open(character_portraits_path, 'w', encoding='utf-8') as f:
                json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)
            print(f"✅ 生成了 {len(character_portraits_registry)} 个角色的肖像\n")
        
        print("="*80)
        print("🎬 步骤 4: 设计分镜")
        print("="*80)
        storyboard_path = os.path.join(pipeline.working_dir, "storyboard.json")
        if os.path.exists(storyboard_path):
            print("🚀 发现已有分镜文件，加载中...")
            try:
                with open(storyboard_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        print("⚠️ 分镜文件为空，将重新生成")
                        storyboard = None
                    else:
                        storyboard = [ShotBriefDescription.model_validate(s) for s in json.loads(content)]
                        print(f"✅ 加载了 {len(storyboard)} 个镜头的分镜（跳过生成）\n")
            except json.JSONDecodeError as e:
                print(f"⚠️ 分镜文件解析失败: {e}，将重新生成")
                storyboard = None
        else:
            user_requirement = "Focus on showing environment changes (coffee cup movement)"
            storyboard = await pipeline.design_storyboard(
                script=TEST_SCRIPT,
                characters=characters,
                scenes=scenes,
                user_requirement=user_requirement,
            )
            with open(storyboard_path, 'w', encoding='utf-8') as f:
                json.dump([s.model_dump() for s in storyboard], f, ensure_ascii=False, indent=4)
            print(f"✅ 设计了 {len(storyboard)} 个镜头的分镜\n")
        
        print("="*80)
        print("📋 步骤 5: 分解视觉描述")
        print("="*80)
        shot_descriptions_path = os.path.join(pipeline.working_dir, "shot_descriptions.json")
        if os.path.exists(shot_descriptions_path):
            print("🚀 发现已有详细分镜文件，加载中...")
            try:
                with open(shot_descriptions_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        print("⚠️ 详细分镜文件为空，将重新生成")
                        shot_descriptions = None
                    else:
                        shot_descriptions = [ShotDescription.model_validate(s) for s in json.loads(content)]
                        print(f"✅ 加载了 {len(shot_descriptions)} 个详细分镜（跳过生成）\n")
            except json.JSONDecodeError as e:
                print(f"⚠️ 详细分镜文件解析失败: {e}，将重新生成")
                shot_descriptions = None
        else:
            shot_descriptions = await pipeline.decompose_visual_descriptions(
                shot_brief_descriptions=storyboard,
                characters=characters,
            )
            with open(shot_descriptions_path, 'w', encoding='utf-8') as f:
                json.dump([s.model_dump() for s in shot_descriptions], f, ensure_ascii=False, indent=4)
            print(f"✅ 分解了 {len(shot_descriptions)} 个镜头的描述\n")
        
        # 设置 style
        pipeline.style = style
        
        # 初始化 frame_events
        for shot in shot_descriptions:
            pipeline.frame_events[shot.idx] = {
                "first_frame": asyncio.Event(),
                "last_frame": asyncio.Event(),
            }
        
        print("="*80)
        print("📹 步骤 6: 构建 Camera Tree")
        print("="*80)
        camera_tree = await pipeline.construct_camera_tree(shot_descriptions)
        print(f"✅ 构建了 Camera Tree，共 {len(camera_tree)} 个相机\n")
        
        print("="*80)
        print("🎬 步骤 7: 生成帧（测试一致性优化）")
        print("="*80 + "\n")
        
        # 为每个 Camera 生成帧
        priority_shot_idxs = [camera.parent_cam_idx for camera in camera_tree if camera.parent_cam_idx is not None]
        frame_generation_tasks = []
        
        for camera in camera_tree:
            print(f"📹 准备为 Camera {camera.idx} 生成帧（镜头 {camera.active_shot_idxs}）")
            task = pipeline.generate_frames_for_single_camera(
                camera=camera,
                shot_descriptions=shot_descriptions,
                characters=characters,
                character_portraits_registry=character_portraits_registry,
                priority_shot_idxs=priority_shot_idxs,
            )
            frame_generation_tasks.append(task)
        
        print("\n" + "="*80)
        print("⏳ 等待所有帧生成完成...")
        print("="*80 + "\n")
        
        # 并发执行所有 Camera 的帧生成
        await asyncio.gather(*frame_generation_tasks)
        
        print("\n" + "="*80)
        print("✅ 所有帧生成完成！")
        print("="*80 + "\n")
        
        # 验证结果
        print("🔍 验证生成的帧...\n")
        verify_generated_frames(pipeline.working_dir, shot_descriptions)
        
        print("\n" + "="*80)
        print("🎉 测试完成！")
        print("="*80)
        print(f"\n📊 测试结果保存在: {pipeline.working_dir}")
        print(f"📝 日志文件: test_consistency_optimization.log")
        print("\n💡 检查要点：")
        print("  1. 查看日志中的 '✨ P1优化' 标记，确认环境参考帧被添加")
        print("  2. 查看日志中的 '✨ P2优化' 标记，确认时序优化生效")
        print("  3. 检查生成的帧图像，验证环境一致性（如咖啡杯位置）")
        print("  4. 对比不同镜头的参考图选择，验证 P5 优化效果")
        print("  5. 检查角色外貌一致性")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        logging.exception("测试过程中发生错误")
        raise


def verify_generated_frames(working_dir: str, shot_descriptions: list):
    """
    验证生成的帧文件
    """
    print("检查项：")
    all_frames_exist = True
    
    for shot in shot_descriptions:
        shot_dir = os.path.join(working_dir, "shots", str(shot.idx))
        
        # 检查首帧
        ff_path = os.path.join(shot_dir, "first_frame.png")
        ff_exists = os.path.exists(ff_path)
        status = "✅" if ff_exists else "❌"
        print(f"  {status} 镜头 {shot.idx} 首帧: {ff_path}")
        
        if not ff_exists:
            all_frames_exist = False
        
        # 检查末帧（如果需要）
        if shot.variation_type in ["medium", "large"]:
            lf_path = os.path.join(shot_dir, "last_frame.png")
            lf_exists = os.path.exists(lf_path)
            status = "✅" if lf_exists else "❌"
            print(f"  {status} 镜头 {shot.idx} 末帧: {lf_path}")
            
            if not lf_exists:
                all_frames_exist = False
        
        # 检查选择器输出
        selector_paths = [
            os.path.join(shot_dir, "first_frame_selector_output.json"),
        ]
        if shot.variation_type in ["medium", "large"]:
            selector_paths.append(os.path.join(shot_dir, "last_frame_selector_output.json"))
        
        for selector_path in selector_paths:
            if os.path.exists(selector_path):
                print(f"  📄 参考图选择记录: {selector_path}")
    
    print()
    if all_frames_exist:
        print("✅ 所有必需的帧都已生成")
    else:
        print("⚠️ 部分帧未生成，请检查日志")


def main():
    """
    主函数
    """
    print("\n" + "="*80)
    print("🧪 ViMax 一致性优化测试 - 完整流程版")
    print("   测试范围：完整 Pipeline（不包含视频生成）")
    print("   流程：场景规划 → 角色提取 → 肖像生成 → 分镜 → 帧生成")
    print("   优化内容：P1（环境参考）+ P2（时序）+ P5（选择器）+ P3/P4（防御）")
    print("="*80 + "\n")
    
    # 运行异步测试
    asyncio.run(test_frame_generation_only())


if __name__ == "__main__":
    main()
