import logging
import os
import asyncio
import tempfile
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from tenacity import retry, stop_after_attempt
from interfaces import CharacterInScene, CharacterAppearance, ImageOutput
from langchain_core.messages import HumanMessage, SystemMessage
from utils.retry import after_func



prompt_template_front = \
"""
Generate a full-body, front-view portrait of character {identifier} based on the following description, with a pure white background. The character should be centered in the image, occupying most of the frame. Gazing straight ahead. Standing with arms relaxed at sides. {emotional_expression}
Features: {features}
Style: {style}
"""

prompt_template_side = \
"""
Generate a full-body, side-view portrait of character {identifier} based on the provided front-view portrait, with a pure white background. The character should be centered in the image, occupying most of the frame. Facing left. Standing with arms relaxed at sides. {emotional_expression}
"""

prompt_template_back = \
"""
Generate a full-body, back-view portrait of character {identifier} based on the provided front-view portrait, with a pure white background. The character should be centered in the image, occupying most of the frame. No facial features should be visible.
"""


# 情绪状态到表情的映射
EMOTIONAL_EXPRESSIONS = {
    "neutral": "Natural, neutral expression.",
    "tired": "Tired, weary expression with slight fatigue visible.",
    "energetic": "Energetic, lively expression with bright eyes.",
    "sad": "Sad, melancholic expression.",
    "angry": "Angry, intense expression.",
    "happy": "Happy, cheerful expression with a smile.",
    "excited": "Excited, enthusiastic expression.",
    "depressed": "Depressed, downcast expression.",
    "anxious": "Anxious, worried expression.",
    "confident": "Confident, self-assured expression.",
    "relaxed": "Relaxed, calm expression.",
}


class CharacterPortraitsGenerator:
    def __init__(
        self,
        image_generator,
    ):
        self.image_generator = image_generator


    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_front_portrait(
        self,
        character: CharacterInScene,
        style: str,
        appearance: Optional[CharacterAppearance] = None,
    ) -> ImageOutput:
        """生成角色的正面肖像
        
        Args:
            character: 角色信息
            style: 风格描述
            appearance: 特定外观（如果为None，使用第一个外观或从dynamic_features创建）
        
        Returns:
            ImageOutput: 生成的图像输出
        """
        logging.info("="*80)
        logging.info(f"🎨 [Agent: CharacterPortraitsGenerator] Generating front portrait for {character.identifier_in_scene}...")
        
        # 确定使用哪个外观
        if appearance is None:
            appearance = character.appearances[0] if character.appearances else None
        
        if appearance:
            logging.info(f"   Using appearance: {appearance.appearance_id} - {appearance.description}")
            logging.info("="*80)
            features = "(static) " + character.static_features + "; (dynamic) " + appearance.dynamic_features
            emotional_expression = EMOTIONAL_EXPRESSIONS.get(
                appearance.emotional_state or "neutral", 
                "Natural expression."
            )
        else:
            # 向后兼容：使用旧的 dynamic_features
            logging.info(f"   Using legacy dynamic_features (backward compatibility)")
            logging.info("="*80)
            features = "(static) " + character.static_features + "; (dynamic) " + character.dynamic_features
            emotional_expression = "Natural expression."
        
        prompt = prompt_template_front.format(
            identifier=character.identifier_in_scene,
            features=features,
            style=style,
            emotional_expression=emotional_expression,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            # size="512x512",
        )
        return image_output

    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_side_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
        appearance: Optional[CharacterAppearance] = None,
    ) -> ImageOutput:
        """生成角色的侧面肖像
        
        Args:
            character: 角色信息
            front_image_path: 正面肖像的路径
            appearance: 特定外观（用于获取情绪表情）
        
        Returns:
            ImageOutput: 生成的图像输出
        """
        # 确定情绪表情
        if appearance is None:
            appearance = character.appearances[0] if character.appearances else None
        
        emotional_expression = "Natural expression."
        if appearance and appearance.emotional_state:
            emotional_expression = EMOTIONAL_EXPRESSIONS.get(
                appearance.emotional_state,
                "Natural expression."
            )
        
        prompt = prompt_template_side.format(
            identifier=character.identifier_in_scene,
            emotional_expression=emotional_expression,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="1024x1024",
        )
        return image_output


    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_back_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
    ) -> ImageOutput:
        """生成角色的背面肖像
        
        Args:
            character: 角色信息
            front_image_path: 正面肖像的路径
        
        Returns:
            ImageOutput: 生成的图像输出
        """
        prompt = prompt_template_back.format(
            identifier=character.identifier_in_scene,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="512x512",
        )
        return image_output
    
    
    async def generate_portraits_for_appearance(
        self,
        character: CharacterInScene,
        appearance: CharacterAppearance,
        style: str,
    ) -> Dict[str, ImageOutput]:
        """为角色的特定外观生成三视图肖像
        
        Args:
            character: 角色信息
            appearance: 特定外观
            style: 风格描述
        
        Returns:
            Dict[str, ImageOutput]: 包含 'front', 'side', 'back' 三个视图的字典
        """
        logging.info("="*80)
        logging.info(f"🎨 [Agent: CharacterPortraitsGenerator] Generating portraits for {character.identifier_in_scene}")
        logging.info(f"   Appearance: {appearance.appearance_id} - {appearance.description}")
        logging.info(f"   Scenes: {appearance.scene_ids if appearance.scene_ids else 'all'}")
        logging.info(f"   Emotional state: {appearance.emotional_state}")
        logging.info("="*80)
        
        # 生成正面肖像
        front_output = await self.generate_front_portrait(character, style, appearance)
        
        # 将正面肖像保存到临时文件，供侧面和背面生成使用
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            front_temp_path = tmp_file.name
            front_output.save(front_temp_path)
        
        try:
            # 生成侧面和背面肖像
            side_output = await self.generate_side_portrait(character, front_temp_path, appearance)
            back_output = await self.generate_back_portrait(character, front_temp_path)
        finally:
            # 清理临时文件
            if os.path.exists(front_temp_path):
                os.unlink(front_temp_path)
        
        return {
            "front": front_output,
            "side": side_output,
            "back": back_output,
        }
    
    
    async def generate_all_appearances_for_character(
        self,
        character: CharacterInScene,
        style: str,
    ) -> Dict[str, Dict[str, ImageOutput]]:
        """为角色的所有外观生成肖像
        
        Args:
            character: 角色信息
            style: 风格描述
        
        Returns:
            Dict[str, Dict[str, ImageOutput]]: 
                外层key是appearance_id，内层是 {'front', 'side', 'back'}
                例如: {
                    'appearance_0': {'front': ImageOutput, 'side': ImageOutput, 'back': ImageOutput},
                    'appearance_1': {'front': ImageOutput, 'side': ImageOutput, 'back': ImageOutput},
                }
        """
        logging.info("="*80)
        logging.info(f"🎭 [Agent: CharacterPortraitsGenerator] Generating ALL appearances for {character.identifier_in_scene}")
        logging.info(f"   Total appearances: {len(character.appearances)}")
        logging.info("="*80)
        
        results = {}
        for appearance in character.appearances:
            portraits = await self.generate_portraits_for_appearance(
                character, appearance, style
            )
            results[appearance.appearance_id] = portraits
            
            logging.info(f"✅ Completed {appearance.appearance_id} for {character.identifier_in_scene}")
        
        logging.info("="*80)
        logging.info(f"🎉 All appearances generated for {character.identifier_in_scene}")
        logging.info("="*80)
        
        return results
