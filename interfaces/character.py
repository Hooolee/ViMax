from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Union, Dict
from PIL import Image


class CharacterAppearance(BaseModel):
    """角色在特定场景的外观
    
    Represents a character's appearance in specific scenes, including:
    - Which scenes use this appearance
    - Dynamic features (clothing, accessories, hairstyle)
    - Emotional state
    - Brief description for identification
    """
    
    appearance_id: str = Field(
        description="外观ID，格式如 'appearance_0', 'appearance_1' / Appearance ID, format like 'appearance_0', 'appearance_1'",
        examples=["appearance_0", "appearance_1", "appearance_2"]
    )
    
    scene_ids: List[int] = Field(
        default_factory=list,
        description="这个外观出现在哪些场景，场景索引从0开始。如果为空列表，表示适用于所有场景（默认外观）/ Which scenes use this appearance, scene indices start from 0. Empty list means applicable to all scenes (default appearance)",
        examples=[[0, 1], [2, 3, 4], []]
    )
    
    dynamic_features: str = Field(
        description="可变特征：服装、发型、配饰等 / Variable features: clothing, hairstyle, accessories, etc.",
        examples=[
            "穿着黑色西装，打着深蓝色领带，头发梳理整齐 / Wearing a black suit with a dark blue tie, hair neatly combed",
            "穿着灰色睡衣，头发凌乱，面容疲惫 / Wearing gray pajamas, messy hair, tired face",
            "Wearing casual jeans and a white t-shirt, sneakers"
        ]
    )
    
    emotional_state: Optional[str] = Field(
        default="neutral",
        description="基础情绪状态 / Basic emotional state",
        examples=["neutral", "tired", "energetic", "sad", "angry", "happy", "excited", "depressed"]
    )
    
    description: Optional[str] = Field(
        default=None,
        description="外观的简短描述，便于识别 / Brief description of the appearance for easy identification",
        examples=["工作装束 / work attire", "居家装束 / casual home wear", "运动装束 / sports outfit", "formal dress"]
    )




class CharacterInScene(BaseModel):
    idx: int = Field(
        description="The index of the character in the scene, starting from 0",
    )
    identifier_in_scene: str = Field(
        description="The identifier for the character in this specific scene, which may differ from the base identifier",
        examples=["Alice", "Bob the Builder"],
    )
    is_visible: bool = Field(
        description="Indicates whether the character is visible in this scene",
        examples=[True, False],
    )
    static_features: str = Field(
        description="The static features of the character in this specific scene, such as facial features and body shape that remain constant or are rarely changed. If the character is not visible, this field can be left empty.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build.",
            "Bob the Builder is a middle-aged man with a sturdy build.",
        ]
    )
    dynamic_features: str = Field(
        default="",
        description="[DEPRECATED - Use 'appearances' field instead] The dynamic features of the character in this specific scene, such as clothing and accessories that may change from scene to scene. This field is kept for backward compatibility.",
        examples=[
            "Wearing a red scarf and a black leather jacket",
        ],
        deprecated=True
    )
    
    # 新增：多套外观支持
    appearances: List[CharacterAppearance] = Field(
        default_factory=list,
        description="角色在不同场景的多套外观。如果为空，将从 dynamic_features 自动创建默认外观 / Multiple appearances of the character in different scenes. If empty, will auto-create default appearance from dynamic_features"
    )

    @model_validator(mode='after')
    def ensure_appearances(self):
        """确保至少有一个外观定义，向后兼容旧数据格式
        
        Ensure at least one appearance is defined, backward compatible with old data format
        """
        if not self.appearances and self.dynamic_features:
            # 从旧的 dynamic_features 创建默认外观（向后兼容）
            # Create default appearance from old dynamic_features (backward compatibility)
            self.appearances = [
                CharacterAppearance(
                    appearance_id="appearance_0",
                    scene_ids=[],  # 空列表表示适用于所有场景 / Empty list means applicable to all scenes
                    dynamic_features=self.dynamic_features,
                    emotional_state="neutral",
                    description="default appearance"
                )
            ]
        elif not self.appearances and not self.dynamic_features:
            # 如果两者都为空，创建一个空的默认外观
            # If both are empty, create an empty default appearance
            self.appearances = [
                CharacterAppearance(
                    appearance_id="appearance_0",
                    scene_ids=[],
                    dynamic_features="",
                    emotional_state="neutral",
                    description="default appearance"
                )
            ]
        return self
    
    def get_appearance_for_scene(self, scene_id: int) -> Optional[CharacterAppearance]:
        """获取指定场景的外观
        
        Get appearance for a specific scene.
        
        Args:
            scene_id: Scene index (0-based)
            
        Returns:
            CharacterAppearance object for the scene, or None if not found
        """
        # 首先查找明确指定该场景的外观
        # First, look for appearances that explicitly specify this scene
        for appearance in self.appearances:
            if scene_id in appearance.scene_ids:
                return appearance
        
        # 如果没找到，查找默认外观（scene_ids 为空的外观）
        # If not found, look for default appearance (appearance with empty scene_ids)
        for appearance in self.appearances:
            if not appearance.scene_ids:
                return appearance
        
        # 如果还是没找到，返回第一个外观（兜底）
        # If still not found, return the first appearance (fallback)
        return self.appearances[0] if self.appearances else None

    def __str__(self):
        # Alice[visible]
        # static features: Alice has long blonde hair and blue eyes, and is of slender build.
        # appearances: 2 appearance(s)
        #   - appearance_0 (scenes: 0, 1): Wearing a red scarf...
        #   - appearance_1 (scenes: 2, 3): Wearing casual clothes...

        s = f"{self.identifier_in_scene}"
        s += "[visible]" if self.is_visible else "[not visible]"
        s += "\n"
        s += f"static features: {self.static_features}\n"
        
        if self.appearances:
            s += f"appearances: {len(self.appearances)} appearance(s)\n"
            for appearance in self.appearances:
                scenes_str = ", ".join(map(str, appearance.scene_ids)) if appearance.scene_ids else "all scenes"
                s += f"  - {appearance.appearance_id} (scenes: {scenes_str}): {appearance.dynamic_features[:50]}...\n"
        else:
            # 向后兼容：如果没有 appearances，显示旧的 dynamic_features
            s += f"dynamic features: {self.dynamic_features}\n"

        return s




class CharacterInEvent(BaseModel):
    index: int = Field(
        description="The index of the character in the event, starting from 0",
    )
    identifier_in_event: str = Field(
        description="The unique identifier for the character in the event",
        examples=["Alice", "Bob the Builder"],
    )

    active_scenes: Dict[int, str] = Field(
        description="A dictionary mapping scene indices to their identifiers in specific scenes.",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="The static features of the character in the event, such as facial features and body shape that remain constant or are rarely changed.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )



class CharacterInNovel(BaseModel):
    index: int = Field(
        description="The index of the character in the novel, starting from 0",
    )
    identifier_in_novel: str = Field(
        description="The unique identifier for the character in the novel",
        examples=["Alice", "Bob the Builder"],
    )

    active_events: Dict[int, str] = Field(
        description="A dictionary mapping event indices to their identifiers in specific events.",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="The static features of the character in the novel, such as facial features and body shape that remain constant or are rarely changed.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )

