from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from interfaces.environment import EnvironmentInScene
    from interfaces.character import CharacterInScene


class SceneDefinition(BaseModel):
    """场景定义，用于统一划分场景
    
    Scene definition for unified scene segmentation.
    This is used to ensure consistent scene_id across different agents.
    """
    scene_id: int = Field(
        description="场景ID，从0开始 / Scene ID, starting from 0",
        examples=[0, 1, 2],
    )
    location: str = Field(
        description="场景地点 / Scene location",
        examples=["办公室内部 / Office interior", "公园 / Park", "Alice的公寓 / Alice's apartment"],
    )
    time_of_day: Optional[str] = Field(
        default=None,
        description="时间段 / Time of day",
        examples=["早晨 / Morning", "下午 / Afternoon", "晚上 / Evening", "深夜 / Late night"],
    )
    description: str = Field(
        description="场景简短描述，包括主要事件 / Brief scene description including main events",
        examples=[
            "John arrives at the office and meets his colleagues",
            "A tense conversation between Alice and Bob in the park",
            "John returns home exhausted after work"
        ],
    )
    script_excerpt: Optional[str] = Field(
        default=None,
        description="该场景对应的剧本片段（可选）/ Script excerpt for this scene (optional)",
    )

    def __str__(self):
        time_str = f", {self.time_of_day}" if self.time_of_day else ""
        return f"Scene {self.scene_id}: {self.location}{time_str} - {self.description}"


class Scene(BaseModel):
    idx: int = Field(
        description="The scene index, starting from 0",
        examples=[0, 1, 2],
    )
    is_last: bool = Field(
        description="Indicates if this is the last scene",
        examples=[False, True],
    )
    environment: "EnvironmentInScene" = Field(
        description="The detailed scene setting, including location and time",
    )
    characters: List["CharacterInScene"] = Field(
        description="A list of characters appearing in the scene, along with their dynamic features like clothing and accessories",
    )
    script: str = Field(
        description="The screenplay script for the scene, including character actions and dialogues. Character names in the script should be enclosed in <>, except for character names within dialogues.",
        examples=[
            "<Jane> paces nervously, clutching a letter. She turns to <John>.\n<Jane>: John, we need to leave tonight.\n<John> shakes his head, stepping toward the window.\n<John>: It's too dangerous.",
            "<Alice> sits quietly, observing the chaos around her. She whispers to <Bob>.\n<Alice>: Bob, do you think they'll find us here?\n<Bob> nods slowly, his expression grim."
        ],
    )

    def __str__(self):
        s = f"Scene {self.idx}:"
        s += f"\nEnvironment: {str(self.environment)}"
        s += f"\nCharacters: {', '.join([str(c) for c in self.characters])}"
        s += f"\nScript: \n{self.script}"
        return s



# class Scene(BaseModel):
#     index: int = Field(
#         description="The index of the scene within the event, starting from 0"
#     )
#     character_indices: List[int] = Field(
#         description="List of indices of characters appearing in this scene, including main characters, supporting characters, and extras.",
#     )
#     environment_index: int = Field(
#         description="The index of the environment where the scene takes place."
#     )
#     key_items_indices: List[int] = Field(
#         default=[],
#         description="List of indices of key items involved in this scene, if any.",
#     )
#     script: str = Field(
#         description="The script of the scene, including actions and dialogues"
#     )


