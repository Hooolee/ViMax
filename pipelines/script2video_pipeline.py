import os
import shutil
import json
import logging
import asyncio
import time
from typing import Optional, Dict, List, Tuple, Literal
from moviepy import VideoFileClip, concatenate_videoclips
from PIL import Image
from agents import *
from agents.best_image_selector import BestImageSelector
import yaml
from interfaces import *
from utils.model_init import init_chat_model_compat
from utils.timer import Timer
import importlib
from utils.timeline import build_timeline, write_timeline_edl, render_timeline

class Script2VideoPipeline:

    # events
    character_portrait_events = {}
    shot_desc_events = {}
    frame_events = {}


    def __init__(
        self,
        chat_model: str,
        image_generator,
        video_generator,
        working_dir: str,
        max_shots: int | None = None,
        interactive_mode: bool = False,
    ):

        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator

        self.scene_planner = ScenePlanner(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.character_portraits_generator = CharacterPortraitsGenerator(image_generator=self.image_generator)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model)
        self.camera_image_generator = CameraImageGenerator(chat_model=self.chat_model, image_generator=self.image_generator, video_generator=self.video_generator)
        self.reference_image_selector = ReferenceImageSelector(chat_model=self.chat_model)
        self.best_image_selector = BestImageSelector(chat_model=self.chat_model)

        self.working_dir = working_dir
        self.max_shots = max_shots
        self.interactive_mode = interactive_mode
        os.makedirs(self.working_dir, exist_ok=True)



    @classmethod
    def init_from_config(
        cls,
        config_path: str,
        output_subdir: str | None = None,
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

        # optional shot limiter for validation/cost control
        max_shots = None
        cfg_max_shots = config.get("max_shots")
        interactive_mode = config.get("interactive_mode", False)
        if isinstance(cfg_max_shots, int) and cfg_max_shots > 0:
            max_shots = cfg_max_shots

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
            max_shots=max_shots,
            interactive_mode=interactive_mode,
        )

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
            
        print("\n" + "="*80)
        print(f"📋 {stage_name}")
        print("="*80)
        if display_content:
            print(display_content)
            print("="*80)
        
        while True:
            choice = input("\n请选择操作:\n  [c] 继续下一步\n  [r] 重新生成\n  [q] 退出程序\n> ").strip().lower()
            if choice in ['c', 'r', 'q']:
                return choice
            print("❌ 无效输入，请输入 c、r 或 q")

    async def __call__(
        self,
        script: str,
        user_requirement: str,
        style: str,
        characters: List[CharacterInScene] = None,
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
        scenes: Optional[List[SceneDefinition]] = None,
    ):
        # 保存 style 供后续使用
        self.style = style
        
        # Step 1: Plan scenes (统一场景划分)
        if scenes is not None:
            # 使用传入的场景定义（来自 Idea2Video）
            print(f"🚀 Using {len(scenes)} scene(s) provided by upstream pipeline.")
            # 保存到文件以便后续缓存
            scenes_path = os.path.join(self.working_dir, "scenes.json")
            if not os.path.exists(scenes_path):
                with open(scenes_path, "w", encoding="utf-8") as f:
                    json.dump([s.model_dump() for s in scenes], f, ensure_ascii=False, indent=4)
                print(f"☑️ Saved {len(scenes)} scene(s) to {scenes_path}.")
        else:
            # 没有传入场景定义，按原有逻辑处理
            scenes_path = os.path.join(self.working_dir, "scenes.json")
            if os.path.exists(scenes_path):
                with open(scenes_path, "r", encoding="utf-8") as f:
                    from interfaces.scene import SceneDefinition
                    scenes = [SceneDefinition.model_validate(s) for s in json.load(f)]
                print(f"🚀 Loaded {len(scenes)} scene(s) from existing file.")
            else:
                print(f"🎬 Planning scene segmentation...")
                scenes = await self.plan_scenes(script=script)
                with open(scenes_path, "w", encoding="utf-8") as f:
                    json.dump([s.model_dump() for s in scenes], f, ensure_ascii=False, indent=4)
                print(f"☑️ Planned {len(scenes)} scene(s) and saved to {scenes_path}.")
        
        # 保存 scenes 供后续使用（用于场景一致性）
        self.scenes = scenes
        self.scenes_dict = {scene.scene_id: scene for scene in scenes}
        
        # Step 2: Extract characters (使用统一的场景定义)
        if characters is None:
            characters = await self.extract_characters(script=script, scenes=scenes)

            # characters_path = os.path.join(self.working_dir, "characters.json")
            # if os.path.exists(characters_path):
            #     with open(characters_path, "r", encoding="utf-8") as f:
            #         characters = [CharacterInScene.model_validate(c) for c in json.load(f)]
            #     print(f"🚀 Loaded {len(characters)} characters from existing file.")
            # else:
            #     print(f"🔍 Extracting characters from script...")
            #     characters = await self.extract_characters(script=script, scenes=scenes)
            #     with open(characters_path, "w", encoding="utf-8") as f:
            #         json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=4)
            #     print(f"☑️ Extracted {len(characters)} characters from script and saved to {characters_path}.")

        # Step 3: Generate character portraits
        if character_portraits_registry is None:
            character_portraits_registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, "r", encoding="utf-8") as f:
                    character_portraits_registry = json.load(f)
                print(f"🚀 Loaded {len(character_portraits_registry)} character portraits from existing file.")
            else:
                print(f"🔍 Generating character portraits...")
                character_portraits_registry = await self.generate_character_portraits(
                    characters=characters,
                    character_portraits_registry=None,
                    style=style,
                )

                with open(character_portraits_registry_path, "w", encoding="utf-8") as f:
                    json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)
                print(f"☑️ Generated {len(character_portraits_registry)} character portraits and saved to {character_portraits_registry_path}.")



        # Step 4: Design storyboard (使用统一的场景定义)
        storyboard = await self.design_storyboard(
            script=script,
            characters=characters,
            scenes=scenes,
            user_requirement=user_requirement,
        )

        # decompose visual descriptions of shots
        shot_descriptions = await self.decompose_visual_descriptions(
            shot_brief_descriptions=storyboard,
            characters=characters,
        )

        # construct camera tree
        camera_tree = await self.construct_camera_tree(
            shot_descriptions=shot_descriptions,
        )

        # continuity checks (180/30 degree rules)
        from utils.continuity import check_continuity
        print("🔎 Running continuity checks (180/30-degree)...")
        continuity_report = check_continuity(shot_descriptions, camera_tree)
        continuity_report_path = os.path.join(self.working_dir, "continuity_report.json")
        with open(continuity_report_path, "w", encoding="utf-8") as f:
            json.dump(continuity_report, f, ensure_ascii=False, indent=4)
        if not continuity_report.get("passed", False):
            print("❌ Continuity check failed. See continuity_report.json for details.")
            for v in continuity_report.get("violations", []):
                print(f" - [Shot {v.get('shot_idx')}] {v.get('type')}: {v.get('message')} | 建议: {v.get('suggestion')}")
            # do not continue to frame generation when failed
            raise RuntimeError("Continuity violations detected; aborting frame generation.")
        else:
            print("✅ Continuity checks passed.")

        priority_shot_idxs = [camera.parent_cam_idx for camera in camera_tree if camera.parent_cam_idx is not None]
        tasks = [
            self.generate_frames_for_single_camera(
                camera=camera,
                shot_descriptions=shot_descriptions,
                characters=characters,
                character_portraits_registry=character_portraits_registry,
                priority_shot_idxs=priority_shot_idxs,
            )
            for camera in camera_tree
        ]

        # 等待所有帧生成完成
        await asyncio.gather(*tasks)

        # 视频生成部分 - 根据 interactive_mode 决定是否顺序生成并交互
        if self.interactive_mode:
            # 交互模式：顺序生成每个分镜视频，并等待用户确认
            for shot_description in shot_descriptions:
                while True:
                    # 生成单个分镜视频
                    await self.generate_video_for_single_shot(
                        shot_description=shot_description,
                    )
                    
                    # 准备显示内容
                    video_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "video.mp4")
                    display_content = f"""
🎬 分镜 #{shot_description.idx} 已生成完成

📝 分镜描述:
  场景: {shot_description.scene_id}
  镜头尺寸: {shot_description.shot_size}
  镜头角度: {shot_description.camera_angle}
  
  首帧描述: {shot_description.ff_desc[:100]}...
  运动描述: {shot_description.motion_desc[:100]}...
  
📁 视频路径: {video_path}
"""
                    
                    # 等待用户确认
                    choice = self.wait_for_user_confirmation(
                        stage_name=f"分镜视频生成 - 第 {shot_description.idx + 1}/{len(shot_descriptions)} 个",
                        display_content=display_content
                    )
                    
                    if choice == 'c':
                        # 继续下一个分镜
                        print(f"✅ 分镜 #{shot_description.idx} 已确认，继续生成下一个分镜...")
                        break
                    elif choice == 'r':
                        # 重新生成 - 删除已生成的视频文件
                        print(f"🔄 重新生成分镜 #{shot_description.idx} 的视频...")
                        if os.path.exists(video_path):
                            os.remove(video_path)
                            print(f"已删除旧视频: {video_path}")
                        # 继续循环重新生成
                    elif choice == 'q':
                        print("⚠️ 用户选择退出，停止视频生成流程")
                        raise KeyboardInterrupt("用户主动退出")
        else:
            # 非交互模式：并发生成所有视频
            video_tasks = [
                self.generate_video_for_single_shot(
                    shot_description=shot_description,
                )
                for shot_description in shot_descriptions
            ]
            await asyncio.gather(*video_tasks)

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        timeline_edl_path = os.path.join(self.working_dir, "timeline.edl")
        if os.path.exists(final_video_path) and os.path.exists(timeline_edl_path):
            print(f"🚀 Skipped rendering; final video & EDL already exist.")
        else:
            print(f"🎬 Building timeline and rendering final video...")
            timeline = build_timeline(shot_descriptions, self.working_dir)
            with open(os.path.join(self.working_dir, "timeline.json"), 'w', encoding='utf-8') as f:
                json.dump(timeline, f, ensure_ascii=False, indent=4)
            write_timeline_edl(timeline, timeline_edl_path)
            render_timeline(timeline, final_video_path)
            print(f"☑️ Rendered final video using timeline, saved to {final_video_path}. EDL: {timeline_edl_path}")

        return final_video_path


    async def generate_frames_for_single_camera(
        self,
        camera: Camera,
        shot_descriptions: List[ShotDescription],
        characters: List[CharacterInScene],
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]],
        priority_shot_idxs: List[int],
    ):
        logging.info("="*80)
        logging.info(f"🖼️ [Pipeline Stage] Generate Frames for Camera {camera.idx}")
        logging.info("="*80)
        # 1. generate the first_frame of the first shot of the camera
        first_shot_idx = camera.active_shot_idxs[0]
        
        # 确保镜头目录存在
        first_shot_dir = os.path.join(self.working_dir, "shots", f"{first_shot_idx}")
        os.makedirs(first_shot_dir, exist_ok=True)
        
        first_shot_ff_path = os.path.join(first_shot_dir, "first_frame.png")

        if os.path.exists(first_shot_ff_path):
            print(f"🚀 Skipped generating first_frame for shot {first_shot_idx}, already exists.")
            self.frame_events[first_shot_idx]["first_frame"].set()

        else:
            print(f"🖼️ Starting first_frame generation for shot {first_shot_idx}...")
            available_image_path_and_text_pairs = []

            for character_idx in shot_descriptions[first_shot_idx].ff_vis_char_idxs:
                identifier_in_scene = characters[character_idx].identifier_in_scene
                registry_item = character_portraits_registry[identifier_in_scene]
                
                # 处理新的嵌套结构（包含 appearance_id）
                # registry_item 现在的结构是: {appearance_id: {view: {path, description}}}
                for appearance_or_view, content in registry_item.items():
                    if isinstance(content, dict) and "path" in content:
                        # 旧格式：直接是 {view: {path, description}}
                        available_image_path_and_text_pairs.append((content["path"], content["description"]))
                    else:
                        # 新格式：{appearance_id: {view: {path, description}}}
                        for view, item in content.items():
                            available_image_path_and_text_pairs.append((item["path"], item["description"]))
            
            # generate the first_frame based on the shot_description.ff_desc
            if camera.parent_shot_idx is not None:
                # generate the first_frame based on the transition video
                parent_shot_idx = camera.parent_shot_idx
                await self.frame_events[parent_shot_idx]["first_frame"].wait()
                parent_shot_ff_path = os.path.join(self.working_dir, "shots", f"{parent_shot_idx}", "first_frame.png")
                transition_video_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", f"transition_video_from_shot_{parent_shot_idx}.mp4")

                if os.path.exists(transition_video_path):
                    print(f"🚀 Skipped generating transition video for shot {first_shot_idx} from shot {parent_shot_idx}, already exists.")
                else:
                    print(f"🖼️ Starting transition video generation for shot {first_shot_idx} from shot {parent_shot_idx}...")
                    transition_video_output = await self.camera_image_generator.generate_transition_video(
                        first_shot_visual_desc=shot_descriptions[parent_shot_idx].visual_desc,
                        second_shot_visual_desc=shot_descriptions[first_shot_idx].visual_desc,
                        first_shot_ff_path=parent_shot_ff_path,
                    )
                    transition_video_output.save(transition_video_path)
                    print(f"☑️ Generated transition video for shot {first_shot_idx} from shot {parent_shot_idx}, saved to {transition_video_path}.")

                new_camera_image_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", f"new_camera_{camera.idx}.png")
                if os.path.exists(new_camera_image_path):
                    print(f"🚀 Skipped generating new camera image for shot {first_shot_idx}, already exists.")
                else:
                    print(f"🖼️ Starting new camera image generation for shot {first_shot_idx}...")
                    new_camera_image = self.camera_image_generator.get_new_camera_image(transition_video_path)
                    new_camera_image.save(new_camera_image_path)
                    print(f"☑️ Generated new camera image for shot {first_shot_idx} (not completed), saved to {new_camera_image_path}.")

                    available_image_path_and_text_pairs.append(
                        (
                            new_camera_image_path,
                            f"The composition and background are correct but some elements may be wrong. The wrong elements should be replaced.\nWrong elements: {camera.missing_info}.\nYou must select this image as the main reference and replace the characters in the image with the provided character portraits. Don't change the background."
                        )
                    )


            # 如果子镜头缺少信息，则需要选择参考图像生成
            if camera.parent_shot_idx is None or camera.missing_info is not None:
                ff_selector_output_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", "first_frame_selector_output.json")
                if os.path.exists(ff_selector_output_path):
                    with open(ff_selector_output_path, 'r', encoding='utf-8') as f:
                        ff_selector_output = json.load(f)
                    print(f"🚀 Loaded existing reference image selection and prompt for first_frame of shot {first_shot_idx} from {ff_selector_output_path}.")
                else:
                    print(f"🔍 Selecting reference images and generating prompt for first_frame of shot {first_shot_idx}...")
                    ff_selector_output = await self.reference_image_selector.select_reference_images_and_generate_prompt(
                        available_image_path_and_text_pairs=available_image_path_and_text_pairs,
                        frame_description=shot_descriptions[first_shot_idx].ff_desc,
                        style=self.style,  # 传入 style
                        scene_id=shot_descriptions[first_shot_idx].scene_id,  # 传入场景 ID 用于外观过滤
                        characters=characters,  # 传入角色列表用于外观过滤
                    )
                    with open(ff_selector_output_path, 'w', encoding='utf-8') as f:
                        json.dump(ff_selector_output, f, ensure_ascii=False, indent=4)

                    print(f"☑️ Selected reference images and generated prompt for first_frame of shot {first_shot_idx}, saved to {ff_selector_output_path}.")

                reference_image_path_and_text_pairs, prompt = ff_selector_output["reference_image_path_and_text_pairs"], ff_selector_output["text_prompt"]
                prefix_prompt = ""
                for i, (image_path, text) in enumerate(reference_image_path_and_text_pairs):
                    prefix_prompt += f"Image {i}: {text}\n"
                
                # Handle None or empty prompt
                if prompt is None or not prompt.strip():
                    logging.warning(f"text_prompt is None for shot {first_shot_idx} first_frame. Using frame description.")
                    prompt = f"Generate an image based on the following description:\n{shot_descriptions[first_shot_idx].ff_desc}"
                
                prompt = f"{prefix_prompt}\n{prompt}" if prefix_prompt else prompt
                reference_image_paths = [item[0] for item in reference_image_path_and_text_pairs]
                
                # Log the final prompt being sent to image generator
                print(f"\n{'='*80}")
                print(f"🎨 Generating first_frame for shot {first_shot_idx}")
                print(f"📝 Final prompt to image generator:")
                print(f"{prompt[:500]}{'...' if len(prompt) > 500 else ''}")
                print(f"🖼️  Using {len(reference_image_paths)} reference images")
                print(f"{'='*80}\n")
                
                ff_image: ImageOutput = await self.image_generator.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    size="1600x900",
                )
                ff_image.save(first_shot_ff_path)
                self.frame_events[first_shot_idx]["first_frame"].set()
                print(f"☑️ Generated first_frame for shot {first_shot_idx}, saved to {first_shot_ff_path}.")
            else:
                shutil.copy(new_camera_image_path, first_shot_ff_path)
                self.frame_events[first_shot_idx]["first_frame"].set()
                print(f"☑️ Generated first_frame for shot {first_shot_idx}, saved to {first_shot_ff_path}.")


        # 2. generate the following frames of the camera
        # P2 优化：改进同一 Camera 内的帧生成顺序，确保时序一致性
        # 策略：按镜头顺序生成，每个镜头的末帧生成后再生成下一个镜头的首帧
        priority_tasks = []
        normal_tasks = []
        
        # 第一个镜头的末帧优先生成（如果需要）
        if shot_descriptions[first_shot_idx].variation_type in ["medium", "large"]:
            task = self.generate_frame_for_single_shot(
                shot_idx=first_shot_idx, 
                frame_type="last_frame", 
                first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                frame_desc=shot_descriptions[first_shot_idx].lf_desc,
                visible_characters=[characters[idx] for idx in shot_descriptions[first_shot_idx].lf_vis_char_idxs],
                character_portraits_registry=character_portraits_registry,
                scene_id=shot_descriptions[first_shot_idx].scene_id,
                shot_descriptions=shot_descriptions,
            )
            # 立即await第一个镜头的末帧，确保后续镜头能看到它
            await task
            print(f"✨ P2优化: 第一个镜头 {first_shot_idx} 的末帧已完成，后续镜头现在可以引用它")

        # 按镜头顺序处理其他镜头
        for shot_idx in camera.active_shot_idxs[1:]:
            # 生成当前镜头的首帧
            first_frame_task = self.generate_frame_for_single_shot(
                    shot_idx=shot_idx, 
                    frame_type="first_frame", 
                    first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                    frame_desc=shot_descriptions[shot_idx].ff_desc,
                    visible_characters=[characters[idx] for idx in shot_descriptions[shot_idx].ff_vis_char_idxs],
                    character_portraits_registry=character_portraits_registry,
                    scene_id=shot_descriptions[shot_idx].scene_id,
                    shot_descriptions=shot_descriptions,
                )
            
            # 如果是优先级镜头，立即等待完成（保持原有的优先级逻辑）
            if shot_idx in priority_shot_idxs:
                await first_frame_task
                print(f"✨ P2优化: 优先级镜头 {shot_idx} 的首帧已完成")
            else:
                normal_tasks.append(first_frame_task)

            # 如果需要末帧，生成末帧
            if shot_descriptions[shot_idx].variation_type in ["medium", "large"]:
                last_frame_task = self.generate_frame_for_single_shot(
                    shot_idx=shot_idx, 
                    frame_type="last_frame", 
                    first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                    frame_desc=shot_descriptions[shot_idx].lf_desc,
                    visible_characters=[characters[idx] for idx in shot_descriptions[shot_idx].lf_vis_char_idxs],
                    character_portraits_registry=character_portraits_registry,
                    scene_id=shot_descriptions[shot_idx].scene_id,
                    shot_descriptions=shot_descriptions,
                )
                normal_tasks.append(last_frame_task)

        # 等待所有非优先级任务完成
        # 注意：这里仍然并发执行，但由于 P1 优化，每个任务都能看到已完成的帧
        if normal_tasks:
            await asyncio.gather(*normal_tasks)



    async def generate_video_for_single_shot(
        self,
        shot_description: ShotDescription,
    ):
        logging.info("="*80)
        logging.info(f"🎥 [Pipeline Stage] Generate Video for Shot {shot_description.idx}")
        logging.info("="*80)
        video_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "video.mp4")
        if os.path.exists(video_path):
            print(f"🚀 Skipped generating video for shot {shot_description.idx}, already exists.")
        else:
            # P4 优化：增强错误处理和超时机制
            try:
                # 等待首帧完成，添加超时保护
                timeout_seconds = 600  # 10分钟超时
                try:
                    await asyncio.wait_for(
                        self.frame_events[shot_description.idx]["first_frame"].wait(),
                        timeout=timeout_seconds
                    )
                    logging.info(f"✅ P4优化: 镜头 {shot_description.idx} 的首帧已就绪")
                except asyncio.TimeoutError:
                    logging.error(f"❌ P4错误: 镜头 {shot_description.idx} 首帧生成超时（{timeout_seconds}秒）")
                    raise RuntimeError(f"Frame generation timeout for shot {shot_description.idx} first_frame")
                
                # 如果需要末帧，也等待末帧完成
                if shot_description.variation_type in ["medium", "large"]:
                    try:
                        await asyncio.wait_for(
                            self.frame_events[shot_description.idx]["last_frame"].wait(),
                            timeout=timeout_seconds
                        )
                        logging.info(f"✅ P4优化: 镜头 {shot_description.idx} 的末帧已就绪")
                    except asyncio.TimeoutError:
                        logging.error(f"❌ P4错误: 镜头 {shot_description.idx} 末帧生成超时（{timeout_seconds}秒）")
                        raise RuntimeError(f"Frame generation timeout for shot {shot_description.idx} last_frame")

                # 验证帧文件是否真的存在
                frame_paths = []
                first_frame_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "first_frame.png")
                if not os.path.exists(first_frame_path):
                    logging.error(f"❌ P4错误: 镜头 {shot_description.idx} 首帧文件不存在: {first_frame_path}")
                    raise FileNotFoundError(f"First frame file not found: {first_frame_path}")
                frame_paths.append(first_frame_path)
                
                if shot_description.variation_type in ["medium", "large"]:
                    last_frame_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "last_frame.png")
                    if not os.path.exists(last_frame_path):
                        logging.error(f"❌ P4错误: 镜头 {shot_description.idx} 末帧文件不存在: {last_frame_path}")
                        raise FileNotFoundError(f"Last frame file not found: {last_frame_path}")
                    frame_paths.append(last_frame_path)

                logging.info(f"✅ P4优化: 所有帧文件已验证存在，开始生成视频")
                print(f"🎬 Starting video generation for shot {shot_description.idx}...")
                video_output = await self.video_generator.generate_single_video(
                    prompt=shot_description.motion_desc + "\n" + shot_description.audio_desc,
                    reference_image_paths=frame_paths,
                )
                video_output.save(video_path)
                print(f"☑️ Generated video for shot {shot_description.idx}, saved to {video_path}.")
                
            except Exception as e:
                logging.error(f"❌ P4错误: 镜头 {shot_description.idx} 视频生成失败: {str(e)}")
                # 触发事件以避免死锁，但抛出异常让上层处理
                raise

    async def generate_frame_for_single_shot(
        self,
        shot_idx: int,
        frame_type: Literal["first_frame", "last_frame"],
        first_shot_ff_path_and_text_pair: Tuple[str, str],
        frame_desc: str,
        visible_characters: List[CharacterInScene],
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]],
        scene_id: Optional[int] = None,  # 场景 ID
        shot_descriptions: Optional[List[ShotDescription]] = None,  # 用于收集已完成的帧
    ) -> ImageOutput:

        # 确保镜头目录存在
        shot_dir = os.path.join(self.working_dir, "shots", f"{shot_idx}")
        os.makedirs(shot_dir, exist_ok=True)
        
        frame_image_path = os.path.join(shot_dir, f"{frame_type}.png")

        if os.path.exists(frame_image_path):
            print(f"🚀 Skipped generating {frame_type} for shot {shot_idx}, already exists.")

        else:
            print(f"🖼️ Starting {frame_type} generation for shot {shot_idx}...")
            available_image_path_and_text_pairs = []
            
            # 获取当前帧的角色朝向信息
            char_orientations = None
            if frame_type == "first_frame":
                char_orientations = shot_descriptions[shot_idx].ff_char_orientations
            elif frame_type == "last_frame":
                char_orientations = shot_descriptions[shot_idx].lf_char_orientations
            
            # 根据角色朝向选择对应的三视图
            for visible_character in visible_characters:
                identifier_in_scene = visible_character.identifier_in_scene
                char_idx = visible_character.idx
                registry_item = character_portraits_registry[identifier_in_scene]
                
                # 确定应该使用哪个视角
                desired_view = "front"  # 默认正面
                if char_orientations and char_idx in char_orientations:
                    desired_view = char_orientations[char_idx]
                
                # 处理新的嵌套结构（包含 appearance_id）
                for appearance_or_view, content in registry_item.items():
                    if isinstance(content, dict) and "path" in content:
                        # 旧格式：直接是 {view: {path, description}}
                        view = appearance_or_view
                        if view == desired_view:
                            available_image_path_and_text_pairs.append((content["path"], content["description"]))
                            logging.info(f"✅ 优化: 为角色 {identifier_in_scene} 选择了 {desired_view} 视角")
                            break
                    else:
                        # 新格式：{appearance_id: {view: {path, description}}}
                        # 在当前 appearance 中查找对应视角
                        if desired_view in content:
                            item = content[desired_view]
                            available_image_path_and_text_pairs.append((item["path"], item["description"]))
                            logging.info(f"✅ 优化: 为角色 {identifier_in_scene} ({appearance_or_view}) 选择了 {desired_view} 视角")
                            break

            # P1 优化：收集已完成的帧作为环境参考（优化版）
            # 只收集前一个镜头的尾帧（如果是同场景）
            current_scene_id = shot_descriptions[shot_idx].scene_id if shot_descriptions and shot_idx < len(shot_descriptions) else None
            
            if shot_idx > 0:
                prev_shot_idx = shot_idx - 1
                prev_scene_id = shot_descriptions[prev_shot_idx].scene_id if shot_descriptions and prev_shot_idx < len(shot_descriptions) else None
                
                # 只有同场景才使用前一个镜头的帧
                if prev_scene_id == current_scene_id:
                    # 优先使用末帧（如果有）
                    lf_event = self.frame_events.get(prev_shot_idx, {}).get("last_frame")
                    if lf_event and lf_event.is_set():
                        lf_path = os.path.join(self.working_dir, "shots", f"{prev_shot_idx}", "last_frame.png")
                        if os.path.exists(lf_path):
                            available_image_path_and_text_pairs.append((
                                lf_path,
                                f"Previous shot {prev_shot_idx} last frame (for temporal continuity)"
                            ))
                            logging.info(f"✅ 优化: 使用前一个镜头 #{prev_shot_idx} 的末帧作为环境参考")
                    else:
                        # 没有末帧，使用首帧
                        ff_event = self.frame_events.get(prev_shot_idx, {}).get("first_frame")
                        if ff_event and ff_event.is_set():
                            ff_path = os.path.join(self.working_dir, "shots", f"{prev_shot_idx}", "first_frame.png")
                            if os.path.exists(ff_path):
                                available_image_path_and_text_pairs.append((
                                    ff_path,
                                    f"Previous shot {prev_shot_idx} first frame (for temporal continuity)"
                                ))
                                logging.info(f"✅ 优化: 使用前一个镜头 #{prev_shot_idx} 的首帧作为环境参考")
                else:
                    logging.info(f"⚠️ 场景切换: 镜头 #{shot_idx} (场景{current_scene_id}) 与前一镜头 #{prev_shot_idx} (场景{prev_scene_id}) 不在同一场景，不使用前一镜头的帧")
            
            # P4 优化：Camera 空间一致性锚点
            # 对于长镜头序列（Camera 内镜头数 >= 5），且当前镜头与首镜头间隔 >= 3，
            # 在同场景的情况下，添加 Camera 首镜头的首帧作为空间参考
            if first_shot_ff_path_and_text_pair is not None:
                first_shot_ff_path, first_shot_ff_desc = first_shot_ff_path_and_text_pair
                
                # 从路径中提取首镜头的 shot_idx
                # 路径格式：/path/to/working_dir/shots/{shot_idx}/first_frame.png
                import re
                match = re.search(r'/shots/(\d+)/first_frame\.png', first_shot_ff_path)
                if match:
                    first_shot_idx = int(match.group(1))
                    first_shot_scene_id = shot_descriptions[first_shot_idx].scene_id if shot_descriptions and first_shot_idx < len(shot_descriptions) else None
                    
                    # 计算当前镜头与首镜头的间隔
                    shot_gap = shot_idx - first_shot_idx
                    
                    # 条件：
                    # 1. 不是首镜头本身
                    # 2. 间隔 >= 3（避免与 P1 优化重复）
                    # 3. 同一场景
                    # 4. 首帧已生成
                    if (shot_idx != first_shot_idx 
                        and shot_gap >= 3 
                        and current_scene_id == first_shot_scene_id
                        and os.path.exists(first_shot_ff_path)):
                        
                        available_image_path_and_text_pairs.append((
                            first_shot_ff_path,
                            f"Camera spatial anchor: first shot {first_shot_idx} first frame (for spatial consistency)"
                        ))
                        logging.info(f"✅ P4优化: 镜头 #{shot_idx} 距离首镜头 #{first_shot_idx} 间隔{shot_gap}，添加Camera空间锚点")
                    else:
                        if shot_gap < 3:
                            logging.debug(f"P4跳过: 镜头 #{shot_idx} 距离首镜头仅{shot_gap}个镜头，由P1优化覆盖")
                        elif current_scene_id != first_shot_scene_id:
                            logging.debug(f"P4跳过: 镜头 #{shot_idx} (场景{current_scene_id}) 与首镜头 (场景{first_shot_scene_id}) 不在同一场景")
            
            # P3 优化：增强场景定义传递的防御性检查
            scene_definition = None
            if scene_id is not None:
                if not hasattr(self, 'scenes_dict'):
                    logging.warning(f"⚠️ P3警告: scenes_dict 未初始化，镜头 {shot_idx} 将缺少场景上下文信息")
                else:
                    scene_definition = self.scenes_dict.get(scene_id)
                    if scene_definition is None:
                        logging.warning(f"⚠️ P3警告: 场景ID {scene_id} 在 scenes_dict 中不存在，镜头 {shot_idx} 将缺少场景上下文信息")
                    else:
                        logging.info(f"✅ P3优化: 成功获取场景 {scene_id} 的定义用于镜头 {shot_idx}")
            else:
                logging.warning(f"⚠️ P3警告: 镜头 {shot_idx} 没有关联的场景ID")

            selector_output_path = os.path.join(self.working_dir, "shots", f"{shot_idx}", f"{frame_type}_selector_output.json")
            if os.path.exists(selector_output_path):
                with open(selector_output_path, 'r', encoding='utf-8') as f:
                    selector_output = json.load(f)
                print(f"🚀 Loaded existing reference image selection and prompt for {frame_type} frame of shot {shot_idx} from {selector_output_path}.")
            else:
                print(f"🔍 Selecting reference images and generating prompt for {frame_type} frame of shot {shot_idx}...")
                selector_output = await self.reference_image_selector.select_reference_images_and_generate_prompt(
                    available_image_path_and_text_pairs=available_image_path_and_text_pairs,
                    frame_description=frame_desc,
                    style=self.style,  # 传入 style
                    scene_id=scene_id,  # 传入场景 ID 用于外观过滤
                    characters=visible_characters,  # 传入可见角色列表
                    scene_definition=scene_definition,  # 传入场景定义用于场景一致性
                )
                with open(selector_output_path, 'w', encoding='utf-8') as f:
                    json.dump(selector_output, f, ensure_ascii=False, indent=4)
                print(f"☑️ Selected reference images and generated prompt for {frame_type} frame of shot {shot_idx}, saved to {selector_output_path}.")

            reference_image_path_and_text_pairs, prompt = selector_output["reference_image_path_and_text_pairs"], selector_output["text_prompt"]
            prefix_prompt = ""
            for i, (image_path, text) in enumerate(reference_image_path_and_text_pairs):
                prefix_prompt += f"Image {i}: {text}\n"
            
            # Handle None or empty prompt
            if prompt is None or not prompt.strip():
                logging.warning(f"text_prompt is None for shot {shot_idx} {frame_type}. Using frame description.")
                prompt = f"Generate an image based on the following description:\n{frame_desc}"
            
            prompt = f"{prefix_prompt}\n{prompt}" if prefix_prompt else prompt
            reference_image_paths = [item[0] for item in reference_image_path_and_text_pairs]

            # Log the final prompt being sent to image generator
            print(f"\n{'='*80}")
            print(f"🎨 Generating {frame_type} for shot {shot_idx}")
            print(f"📝 Final prompt to image generator:")
            print(f"{prompt[:500]}{'...' if len(prompt) > 500 else ''}")
            print(f"🖼️  Using {len(reference_image_paths)} reference images")
            print(f"{'='*80}\n")

            # multi-sample and select best
            n_candidates = 3
            shot_dir = os.path.join(self.working_dir, "shots", f"{shot_idx}")
            candidate_paths = []
            for k in range(n_candidates):
                candidate_output: ImageOutput = await self.image_generator.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    size="1600x900",
                )
                candidate_path = os.path.join(shot_dir, f"{frame_type}_candidate_{k}.png")
                candidate_output.save(candidate_path)
                candidate_paths.append(candidate_path)

            # select best using BestImageSelector
            reference_image_path_and_text_pairs = selector_output["reference_image_path_and_text_pairs"]
            selection_reason = {
                "selected": None,
                "reason": None,
                "candidates": candidate_paths,
            }
            try:
                best_path = await self.best_image_selector(
                    reference_image_path_and_text_pairs=reference_image_path_and_text_pairs,
                    target_description=frame_desc,
                    candidate_image_paths=candidate_paths,
                )
                selection_reason["selected"] = best_path
                selection_reason["reason"] = getattr(self.best_image_selector, "last_reason", None)
            except Exception as e:
                print(f"⚠️ Best image selection failed for shot {shot_idx} {frame_type}, fallback to first candidate. Error: {e}")
                best_path = candidate_paths[0]
                selection_reason["selected"] = best_path
                selection_reason["reason"] = f"fallback_first_candidate_due_to_error: {e}"

            # persist reason and finalize chosen frame
            selection_reason_path = os.path.join(shot_dir, f"{frame_type}_selection_reason.json")
            with open(selection_reason_path, 'w', encoding='utf-8') as f:
                json.dump(selection_reason, f, ensure_ascii=False, indent=4)
            shutil.copy(best_path, frame_image_path)
            print(f"☑️ Generated {frame_type} frame for shot {shot_idx}, saved to {frame_image_path} (best of {n_candidates}).")


        self.frame_events[shot_idx][frame_type].set()
        return frame_image_path


    async def construct_camera_tree(
        self,
        shot_descriptions: List[ShotDescription],
    ):
        logging.info("="*80)
        logging.info("🎥 [Pipeline Stage] Construct Camera Tree")
        logging.info("="*80)
        camera_tree_path = os.path.join(self.working_dir, "camera_tree.json")

        if os.path.exists(camera_tree_path):
            with open(camera_tree_path, "r", encoding="utf-8") as f:
                camera_tree = json.load(f)
            camera_tree = [Camera.model_validate(camera) for camera in camera_tree]
            print(f"🚀 Loaded {len(camera_tree)} cameras from existing file.")
            return camera_tree

        cameras: List[Camera] = []
        for shot_description in shot_descriptions:
            if shot_description.cam_idx not in [camera.idx for camera in cameras]:
                cameras.append(Camera(idx=shot_description.cam_idx, active_shot_idxs=[shot_description.idx]))
            else:
                cameras[shot_description.cam_idx].active_shot_idxs.append(shot_description.idx)

        camera_tree = await self.camera_image_generator.construct_camera_tree(cameras=cameras, shot_descs=shot_descriptions)
        with open(camera_tree_path, "w", encoding="utf-8") as f:
            json.dump([camera.model_dump() for camera in camera_tree], f, ensure_ascii=False, indent=4)
        print(f"✅ Constructed camera tree and saved to {camera_tree_path}.")
        return camera_tree




    async def plan_scenes(
        self,
        script: str,
    ):
        """
        规划场景划分
        
        Plan scene segmentation from the script.
        """
        from interfaces.scene import SceneDefinition
        
        logging.info("="*80)
        logging.info(f"🎬 [Pipeline Stage] Planning Scene Segmentation")
        logging.info("="*80)
        
        scenes = await self.scene_planner.plan_scenes(script)
        
        return scenes


    async def extract_characters(
        self,
        script: str,
        scenes: List = None,
    ):
        """
        提取人物信息
        
        Extract character information from the script.
        If scenes are provided, characters will use these scene IDs.
        """
        from interfaces.scene import SceneDefinition
        
        save_path = os.path.join(self.working_dir, "characters.json")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
            characters = [CharacterInScene.model_validate(character) for character in characters]
            print(f"🚀 Loaded {len(characters)} characters from existing file.")
        else:
            characters = await self.character_extractor.extract_characters(script, scenes=scenes)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump([character.model_dump() for character in characters], f, ensure_ascii=False, indent=4)
            print(f"✅ Extracted {len(characters)} characters from script and saved to {save_path}.")

        for character in characters:
            self.character_portrait_events[character.idx] = asyncio.Event()

        return characters


    async def generate_character_portraits(
        self,
        characters: List[CharacterInScene],
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]],
        style: str,
    ):
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
        return character_portraits_registry


    async def generate_portraits_for_single_character(
        self,
        character: CharacterInScene,
        style: str,
    ):
        """为单个角色生成所有外观的肖像
        
        该方法会为角色的每个外观生成独立的三视图肖像，并保存到对应的目录中。
        """
        character_base_dir = os.path.join(
            self.working_dir, 
            "character_portraits", 
            f"{character.idx}_{character.identifier_in_scene}"
        )
        os.makedirs(character_base_dir, exist_ok=True)

        result = {character.identifier_in_scene: {}}

        # 为每个外观生成肖像
        for appearance in character.appearances:
            appearance_dir = os.path.join(character_base_dir, appearance.appearance_id)
            os.makedirs(appearance_dir, exist_ok=True)

            front_portrait_path = os.path.join(appearance_dir, "front.png")
            side_portrait_path = os.path.join(appearance_dir, "side.png")
            back_portrait_path = os.path.join(appearance_dir, "back.png")

            # 检查是否已存在
            if all(os.path.exists(p) for p in [front_portrait_path, side_portrait_path, back_portrait_path]):
                print(f"🚀 Skipped generating portraits for {character.identifier_in_scene} - {appearance.appearance_id}, already exists.")
            else:
                print(f"🎨 Generating portraits for {character.identifier_in_scene} - {appearance.appearance_id}...")
                
                # 生成正面肖像
                if not os.path.exists(front_portrait_path):
                    front_portrait_output = await self.character_portraits_generator.generate_front_portrait(
                        character, style, appearance
                    )
                    front_portrait_output.save(front_portrait_path)

                # 生成侧面肖像
                if not os.path.exists(side_portrait_path):
                    side_portrait_output = await self.character_portraits_generator.generate_side_portrait(
                        character, front_portrait_path, appearance
                    )
                    side_portrait_output.save(side_portrait_path)

                # 生成背面肖像
                if not os.path.exists(back_portrait_path):
                    back_portrait_output = await self.character_portraits_generator.generate_back_portrait(
                        character, front_portrait_path
                    )
                    back_portrait_output.save(back_portrait_path)

                print(f"☑️ Completed portraits for {character.identifier_in_scene} - {appearance.appearance_id}")

            # 添加到结果中
            # 注意：这里的 key 格式变更为包含 appearance_id
            appearance_key = appearance.appearance_id
            if appearance_key not in result[character.identifier_in_scene]:
                result[character.identifier_in_scene][appearance_key] = {}
            
            scenes_str = f"scenes {appearance.scene_ids}" if appearance.scene_ids else "all scenes"
            result[character.identifier_in_scene][appearance_key] = {
                "front": {
                    "path": front_portrait_path,
                    "description": f"A front view portrait of {character.identifier_in_scene} ({appearance.description}, {scenes_str}).",
                },
                "side": {
                    "path": side_portrait_path,
                    "description": f"A side view portrait of {character.identifier_in_scene} ({appearance.description}, {scenes_str}).",
                },
                "back": {
                    "path": back_portrait_path,
                    "description": f"A back view portrait of {character.identifier_in_scene} ({appearance.description}, {scenes_str}).",
                },
            }

        self.character_portrait_events[character.idx].set()
        print(f"✅ Completed all appearance portraits for {character.identifier_in_scene} ({len(character.appearances)} appearance(s)).")

        return result




    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        scenes: List = None,
        user_requirement: str = None,
    ):
        """
        设计分镜
        
        Design storyboard based on the script.
        If scenes are provided, shots will be assigned to these scene IDs.
        """
        from interfaces.scene import SceneDefinition
        
        logging.info("="*80)
        logging.info("📋 [Pipeline Stage] Design Storyboard")
        logging.info("="*80)
        storyboard_path = os.path.join(self.working_dir, "storyboard.json")
        if os.path.exists(storyboard_path):
            with open(storyboard_path, 'r', encoding='utf-8') as f:
                storyboard = json.load(f)
            storyboard = [ShotBriefDescription.model_validate(shot) for shot in storyboard]
            print(f"🚀 Loaded {len(storyboard)} shot brief descriptions from existing file.")
        else:
            print(f"🔍 Designing storyboard...")
            storyboard = await self.storyboard_artist.design_storyboard(
                script=script,
                characters=characters,
                scenes=scenes,
                user_requirement=user_requirement,
                retry_timeout=150,
            )
            with open(storyboard_path, 'w', encoding='utf-8') as f:
                json.dump([shot.model_dump() for shot in storyboard], f, ensure_ascii=False, indent=4)
            print(f"✅ Designed storyboard and saved to {storyboard_path}.")


        # apply shot limit if configured
        if self.max_shots is not None:
            storyboard = storyboard[: self.max_shots]

        for shot_brief_description in storyboard:
            self.shot_desc_events[shot_brief_description.idx] = asyncio.Event()

        return storyboard



    async def decompose_visual_descriptions(
        self,
        shot_brief_descriptions: List[ShotBriefDescription],
        characters: List[CharacterInScene],
    ):
        logging.info("="*80)
        logging.info("🎬 [Pipeline Stage] Decompose Visual Descriptions")
        logging.info("="*80)
        tasks = [
            self.decompose_visual_description_for_single_shot_brief_description(shot_brief_description, characters)
            for shot_brief_description in shot_brief_descriptions
        ]

        shot_descriptions = await asyncio.gather(*tasks)
        return shot_descriptions


    async def decompose_visual_description_for_single_shot_brief_description(
        self,
        shot_brief_description: ShotBriefDescription,
        characters: List[CharacterInScene],
    ):
        shot_description_path = os.path.join(self.working_dir, "shots", f"{shot_brief_description.idx}", "shot_description.json")
        os.makedirs(os.path.dirname(shot_description_path), exist_ok=True)

        if os.path.exists(shot_description_path):
            with open(shot_description_path, 'r', encoding='utf-8') as f:
                shot_description = ShotDescription.model_validate(json.load(f))
            print(f"🚀 Loaded shot {shot_brief_description.idx} description from existing file.")
        else:
            shot_description = await self.storyboard_artist.decompose_visual_description(
                shot_brief_desc=shot_brief_description,
                characters=characters,
                retry_timeout=120,
            )
            with open(shot_description_path, 'w', encoding='utf-8') as f:
                json.dump(shot_description.model_dump(), f, ensure_ascii=False, indent=4)
            print(f"✅ Decomposed visual description for shot {shot_brief_description.idx} and saved to {shot_description_path}.")

        self.shot_desc_events[shot_brief_description.idx].set()

        if shot_description.variation_type in ["medium", "large"]:
            self.frame_events[shot_brief_description.idx] = {
                "first_frame": asyncio.Event(),
                "last_frame": asyncio.Event(),
            }
        else:
            self.frame_events[shot_brief_description.idx] = {
                "first_frame": asyncio.Event(),
            }

        return shot_description
