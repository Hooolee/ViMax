import os
import logging
from agents import Screenwriter, CharacterExtractor, CharacterPortraitsGenerator, ScenePlanner
from pipelines.script2video_pipeline import Script2VideoPipeline
from interfaces import CharacterInScene, SceneDefinition
from typing import List, Dict, Optional
import asyncio
import json
from moviepy import VideoFileClip, concatenate_videoclips
import yaml
from utils.model_init import init_chat_model_compat
import importlib
import sys

class Idea2VideoPipeline:
    def __init__(
        self,
        chat_model: str,
        image_generator: str,
        video_generator: str,
        working_dir: str,
        max_scenes: int | None = None,
        interactive_mode: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.working_dir = working_dir
        self.max_scenes = max_scenes
        self.interactive_mode = interactive_mode
        os.makedirs(self.working_dir, exist_ok=True)

        self.screenwriter = Screenwriter(chat_model=self.chat_model)
        self.scene_planner = ScenePlanner(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.character_portraits_generator = CharacterPortraitsGenerator(image_generator=self.image_generator)
    
    def wait_for_user_confirmation(self, stage_name: str):
        """
        等待用户确认是否继续下一步
        """
        if not self.interactive_mode:
            return 'continue'
        
        print("\n" + "="*80)
        print(f"🎯 [{stage_name}] 阶段已完成！")
        print("="*80)
        print("请选择：")
        print("  [c] 继续下一步")
        print("  [r] 重新运行当前步骤")
        print("  [q] 退出程序")
        print("="*80)
        
        while True:
            try:
                choice = input("请输入选项 (c/r/q): ").strip().lower()
                if choice == 'c':
                    print(f"✅ 继续执行下一步...\n")
                    return 'continue'
                elif choice == 'r':
                    print(f"🔄 准备重新运行 [{stage_name}] 阶段...\n")
                    return 'retry'
                elif choice == 'q':
                    print(f"👋 用户选择退出程序")
                    sys.exit(0)
                else:
                    print("❌ 无效的选项，请输入 c、r 或 q")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 用户中断，退出程序")
                sys.exit(0)

    @classmethod
    def init_from_config(
        cls,
        config_path: str,
        output_subdir: str | None = None,
        interactive_mode: bool = True,
    ):
        from utils.config import resolve_env_vars
        with open(config_path, "r") as f:
            config = resolve_env_vars(yaml.safe_load(f))

        chat_model_args = config["chat_model"]["init_args"]
        chat_model = init_chat_model_compat(**chat_model_args)

        image_generator_cls_module, image_generator_cls_name = config["image_generator"]["class_path"].rsplit(".", 1)
        image_generator_cls = getattr(importlib.import_module(image_generator_cls_module), image_generator_cls_name)
        image_generator_args = config["image_generator"]["init_args"]
        image_generator = image_generator_cls(**image_generator_args)

        video_generator_cls_module, video_generator_cls_name = config["video_generator"]["class_path"].rsplit(".", 1)
        video_generator_cls = getattr(importlib.import_module(video_generator_cls_module), video_generator_cls_name)
        video_generator_args = config["video_generator"]["init_args"]
        video_generator = video_generator_cls(**video_generator_args)

        # optional validation/limiter config
        max_scenes = None
        if isinstance(config.get("max_scenes"), int) and config["max_scenes"] > 0:
            max_scenes = config["max_scenes"]
            logging.info(f"⚙️  max_scenes set to {max_scenes}")
        elif config.get("validate_first_scene") is True:
            max_scenes = 1
            logging.info(f"⚙️  validate_first_scene=True, max_scenes set to 1")
        else:
            logging.info(f"⚙️  max_scenes not set, will process all scenes")

        # 拼接工作目录：基础路径 + 子目录
        base_working_dir = config["working_dir"]
        if output_subdir:
            working_dir = os.path.join(base_working_dir, output_subdir)
        else:
            working_dir = base_working_dir

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=working_dir,
            max_scenes=max_scenes,
            interactive_mode=interactive_mode,
        )

    async def plan_scenes(
        self,
        script: str,
    ) -> List[SceneDefinition]:
        """
        统一规划场景，为整个 Idea2Video 流程提供一致的场景定义
        """
        while True:
            logging.info("="*80)
            logging.info("🎬 [Pipeline Stage] Planning Scene Segmentation")
            logging.info("="*80)
            save_path = os.path.join(self.working_dir, "scenes.json")

            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as f:
                    scenes = json.load(f)
                scenes = [SceneDefinition.model_validate(scene) for scene in scenes]
                print(f"🚀 Loaded {len(scenes)} scenes from existing file.")
            else:
                scenes = await self.scene_planner.plan_scenes(script)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump([scene.model_dump() for scene in scenes], f, ensure_ascii=False, indent=4)
                print(f"✅ Planned {len(scenes)} scenes and saved to {save_path}.")
            
            # 显示场景信息
            print("\n" + "-"*80)
            print(f"📄 场景规划：共 {len(scenes)} 个场景")
            print("-"*80)
            for scene in scenes:
                print(f"场景 {scene.scene_id}: {scene.location} - {scene.time_of_day}")
                print(f"  描述: {scene.description[:100]}...")
            print("-"*80)
            
            # 等待用户确认
            action = self.wait_for_user_confirmation("Plan Scenes")
            if action == 'continue':
                return scenes
            elif action == 'retry':
                # 删除保存的文件以便重新生成
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue

    async def extract_characters(
        self,
        story: str,
        scenes: Optional[List[SceneDefinition]] = None,
    ):
        while True:
            logging.info("="*80)
            logging.info("👥 [Pipeline Stage] Extract Characters")
            logging.info("="*80)
            save_path = os.path.join(self.working_dir, "characters.json")

            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as f:
                    characters = json.load(f)
                characters = [CharacterInScene.model_validate(character) for character in characters]
                print(f"🚀 Loaded {len(characters)} characters from existing file.")
            else:
                characters = await self.character_extractor.extract_characters(story, scenes=scenes)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump([character.model_dump() for character in characters], f, ensure_ascii=False, indent=4)
                print(f"✅ Extracted {len(characters)} characters from story and saved to {save_path}.")
            
            # 显示角色信息
            print("\n" + "-"*80)
            print(f"📄 角色提取：共 {len(characters)} 个角色")
            print("-"*80)
            for character in characters:
                print(f"角色 {character.idx}: {character.identifier_in_scene}")
                if character.static_features:
                    desc_preview = character.static_features[:100] + "..." if len(character.static_features) > 100 else character.static_features
                    print(f"  静态特征: {desc_preview}")
                if character.appearances:
                    print(f"  外观数量: {len(character.appearances)}")
            print("-"*80)
            
            # 等待用户确认
            action = self.wait_for_user_confirmation("Extract Characters")
            if action == 'continue':
                return characters
            elif action == 'retry':
                # 删除保存的文件以便重新生成
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue


    async def generate_character_portraits(
        self,
        characters: List[CharacterInScene],
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]],
        style: str,
    ):
        while True:
            logging.info("="*80)
            logging.info("🎨 [Pipeline Stage] Generate Character Portraits")
            logging.info("="*80)
            character_portraits_registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")
            if character_portraits_registry is None:
                if os.path.exists(character_portraits_registry_path):
                    with open(character_portraits_registry_path, 'r', encoding='utf-8') as f:
                        character_portraits_registry = json.load(f)
                else:
                    character_portraits_registry = {}


            tasks = [
                self.generate_portraits_for_single_character(character, style)
                for character in characters
                if character.identifier_in_scene not in character_portraits_registry
            ]
            if tasks:
                for future in asyncio.as_completed(tasks):
                    character_portraits_registry.update(await future)
                    with open(character_portraits_registry_path, 'w', encoding='utf-8') as f:
                        json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)

                print(f"✅ Completed character portrait generation for {len(characters)} characters.")
            else:
                print("🚀 All characters already have portraits, skipping portrait generation.")
            
            # 显示角色肖像信息
            print("\n" + "-"*80)
            print(f"📄 角色肖像生成：共 {len(character_portraits_registry)} 个角色")
            print("-"*80)
            for char_name, portraits in character_portraits_registry.items():
                print(f"角色: {char_name}")
                for view, info in portraits.items():
                    print(f"  {view}: {info['path']}")
            print("-"*80)
            
            # 等待用户确认
            action = self.wait_for_user_confirmation("Generate Character Portraits")
            if action == 'continue':
                return character_portraits_registry
            elif action == 'retry':
                # 删除保存的文件以便重新生成
                if os.path.exists(character_portraits_registry_path):
                    os.remove(character_portraits_registry_path)
                # 删除所有角色肖像目录
                character_portraits_dir = os.path.join(self.working_dir, "character_portraits")
                if os.path.exists(character_portraits_dir):
                    import shutil
                    shutil.rmtree(character_portraits_dir)
                character_portraits_registry = None
                continue



    async def develop_story(
        self,
        idea: str,
        user_requirement: str,
    ):
        while True:
            logging.info("="*80)
            logging.info("📖 [Pipeline Stage] Develop Story")
            logging.info("="*80)
            save_path = os.path.join(self.working_dir, "story.txt")
            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as f:
                    story = f.read()
                print(f"🚀 Loaded story from existing file.")
            else:
                print("🧠 Developing story...")
                story = await self.screenwriter.develop_story(idea=idea, user_requirement=user_requirement)
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(story)
                print(f"✅ Developed story and saved to {save_path}.")
            
            # 显示故事内容预览
            print("\n" + "-"*80)
            print("📄 故事内容预览：")
            print("-"*80)
            print(story[:500] + "..." if len(story) > 500 else story)
            print("-"*80)
            
            # 等待用户确认
            action = self.wait_for_user_confirmation("Develop Story")
            if action == 'continue':
                return story
            elif action == 'retry':
                # 删除保存的文件以便重新生成
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue


    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: str,
    ):
        while True:
            logging.info("="*80)
            logging.info("📝 [Pipeline Stage] Write Script Based on Story")
            logging.info("="*80)
            save_path = os.path.join(self.working_dir, "script.json")
            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as f:
                    script = json.load(f)
                print(f"🚀 Loaded script from existing file.")
            else:
                print("🧠 Writing script based on story...")
                script = await self.screenwriter.write_script_based_on_story(story=story, user_requirement=user_requirement)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(script, f, ensure_ascii=False, indent=4)
                print(f"✅ Written script based on story and saved to {save_path}.")
            
            # 显示脚本信息
            print("\n" + "-"*80)
            print(f"📄 脚本信息：共 {len(script)} 个场景")
            print("-"*80)
            for idx, scene in enumerate(script[:3]):  # 只显示前3个场景
                scene_preview = scene[:200] + "..." if len(scene) > 200 else scene
                print(f"场景 {idx + 1}: {scene_preview}")
            if len(script) > 3:
                print(f"... (还有 {len(script) - 3} 个场景)")
            print("-"*80)
            
            # 等待用户确认
            action = self.wait_for_user_confirmation("Write Script")
            if action == 'continue':
                return script
            elif action == 'retry':
                # 删除保存的文件以便重新生成
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue


    async def generate_portraits_for_single_character(
        self,
        character: CharacterInScene,
        style: str,
    ):
        character_dir = os.path.join(self.working_dir, "character_portraits", f"{character.idx}_{character.identifier_in_scene}")
        os.makedirs(character_dir, exist_ok=True)

        front_portrait_path = os.path.join(character_dir, "front.png")
        if os.path.exists(front_portrait_path):
            pass
        else:
            front_portrait_output = await self.character_portraits_generator.generate_front_portrait(character, style)
            front_portrait_output.save(front_portrait_path)


        side_portrait_path = os.path.join(character_dir, "side.png")
        if os.path.exists(side_portrait_path):
            pass
        else:
            side_portrait_output = await self.character_portraits_generator.generate_side_portrait(character, front_portrait_path)
            side_portrait_output.save(side_portrait_path)

        back_portrait_path = os.path.join(character_dir, "back.png")
        if os.path.exists(back_portrait_path):
            pass
        else:
            back_portrait_output = await self.character_portraits_generator.generate_back_portrait(character, front_portrait_path)
            back_portrait_output.save(back_portrait_path)

        print(f"☑️ Completed character portrait generation for {character.identifier_in_scene}.")

        return {
            character.identifier_in_scene: {
                "front": {
                    "path": front_portrait_path,
                    "description": f"A front view portrait of {character.identifier_in_scene}.",
                },
                "side": {
                    "path": side_portrait_path,
                    "description": f"A side view portrait of {character.identifier_in_scene}.",
                },
                "back": {
                    "path": back_portrait_path,
                    "description": f"A back view portrait of {character.identifier_in_scene}.",
                },
            }
        }

    async def __call__(
        self,
        idea: str,
        user_requirement: str,
        style: str,
    ):

        # 步骤 1: 发展故事
        story = await self.develop_story(idea=idea, user_requirement=user_requirement)

        # 步骤 2: 编写剧本（按场景分段）
        scene_scripts = await self.write_script_based_on_story(story=story, user_requirement=user_requirement)

        # 步骤 3: 统一场景规划
        # 将所有场景剧本合并为完整剧本，用于场景规划
        full_script = "\n\n".join(scene_scripts)
        scenes = await self.plan_scenes(script=full_script)
        
        # 验证场景数量是否匹配
        if len(scenes) != len(scene_scripts):
            logging.warning(
                f"⚠️ Scene count mismatch: ScenePlanner identified {len(scenes)} scenes, "
                f"but Screenwriter wrote {len(scene_scripts)} scene scripts. "
                f"This may cause scene_id inconsistencies."
            )

        # 步骤 4: 提取角色（使用统一的场景定义）
        characters = await self.extract_characters(story=story, scenes=scenes)

        # 步骤 5: 生成角色肖像
        character_portraits_registry = await self.generate_character_portraits(
            characters=characters,
            character_portraits_registry=None,
            style=style,
        )

        all_video_paths = []

        # optionally limit scenes for validation/cost control
        limited_scene_scripts = scene_scripts
        limited_scenes = scenes
        if self.max_scenes is not None:
            limited_scene_scripts = scene_scripts[: self.max_scenes]
            limited_scenes = scenes[: self.max_scenes]
            logging.info(f"⚠️  Limited scenes: processing {len(limited_scene_scripts)} out of {len(scene_scripts)} scenes (max_scenes={self.max_scenes})")
        else:
            logging.info(f"📝 Processing all {len(scene_scripts)} scenes (max_scenes not set)")

        # 步骤 6: 为每个场景生成视频（传递对应的场景定义）
        for idx, scene_script in enumerate(limited_scene_scripts):
            while True:
                scene_working_dir = os.path.join(self.working_dir, f"scene_{idx}")
                os.makedirs(scene_working_dir, exist_ok=True)
                
                # 获取当前场景的定义
                scene_definition = limited_scenes[idx] if idx < len(limited_scenes) else None
                if scene_definition:
                    logging.info(f"📍 Processing Scene {idx}: {scene_definition.location} - {scene_definition.time_of_day}")
                
                script2video_pipeline = Script2VideoPipeline(
                    chat_model=self.chat_model,
                    image_generator=self.image_generator,
                    video_generator=self.video_generator,
                    working_dir=scene_working_dir,
                    interactive_mode=self.interactive_mode,
                )
                
                # 将统一的场景定义传递给 Script2Video
                # 注意：这里传递单个场景的定义
                scene_video_path = await script2video_pipeline(
                    script=scene_script,
                    user_requirement=user_requirement,
                    style=style,
                    characters=characters,
                    character_portraits_registry=character_portraits_registry,
                    scenes=[scene_definition] if scene_definition else None,  # 传递单场景定义
                )
                
                # 显示场景视频生成信息
                print("\n" + "-"*80)
                print(f"📄 场景 {idx + 1}/{len(limited_scene_scripts)} 视频已生成")
                print(f"视频路径: {scene_video_path}")
                print("-"*80)
                
                # 等待用户确认
                action = self.wait_for_user_confirmation(f"Scene {idx + 1} Video Generation")
                if action == 'continue':
                    all_video_paths.append(scene_video_path)
                    break
                elif action == 'retry':
                    # 删除场景工作目录以便重新生成
                    if os.path.exists(scene_working_dir):
                        import shutil
                        shutil.rmtree(scene_working_dir)
                    continue

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path):
            print(f"🚀 Skipped concatenating videos, already exists.")
        else:
            if len(all_video_paths) == 1:
                # single-scene validation: just copy/rename by re-encode using moviepy for consistency
                print(f"🎬 Single-scene output; writing final_video.mp4 from the only scene...")
                clip = VideoFileClip(all_video_paths[0])
                clip.write_videofile(final_video_path)
                print(f"☑️ Wrote single-scene final video to {final_video_path}.")
            else:
                print(f"🎬 Starting concatenating videos...")
                video_clips = [VideoFileClip(path) for path in all_video_paths]
                final_video = concatenate_videoclips(video_clips)
                final_video.write_videofile(final_video_path)
                print(f"☑️ Concatenated videos, saved to {final_video_path}.")
        
        # 最终视频生成完成，显示信息
        print("\n" + "="*80)
        print("🎉 所有阶段已完成！最终视频已生成！")
        print("="*80)
        print(f"📹 最终视频路径: {final_video_path}")
        print("="*80)
        
        # 等待用户确认完成
        self.wait_for_user_confirmation("Final Video Generation Complete")
        
        return final_video_path
