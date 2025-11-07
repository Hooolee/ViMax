import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List
from tenacity import retry, stop_after_attempt
from interfaces import CharacterInScene
from interfaces.scene import SceneDefinition
from langchain_core.messages import HumanMessage, SystemMessage

from utils.retry import after_func
from utils.prompt_logger import log_agent_prompt


system_prompt_template_extract_characters = \
"""
[角色]
您是一名顶级的电影剧本分析专家。

[任务]
您的任务是分析提供的剧本并提取所有相关的角色信息，包括如果角色在不同场景中服装、发型或情绪状态发生变化时的多次出现。

[输入]
您将收到一个包含在<SCRIPT>和</SCRIPT>标签内的剧本。

以下是输入的简单示例：

<SCRIPT>
场景0：办公室内部 - 早晨
约翰穿着一身笔挺的黑色西装和深蓝色领带走进办公室。他的头发梳理整齐，拎着一个公文包。他看起来自信而专业。

场景1：办公室内部 - 下午
约翰继续在办公桌前工作，仍然穿着黑色西装。随着一天过去，他稍微松了松领带。

场景2：约翰的公寓 - 晚上
约翰走进他的公寓，现在穿着灰色运动裤和一件旧T恤。他的头发凌乱，看起来精疲力尽。他瘫倒在沙发上。

场景3：约翰的公寓 - 深夜
仍然穿着休闲的家居服，约翰点了外卖。他显得疲惫而沉默。
</SCRIPT>

[输出格式]
{format_instructions}

[重要：多次出现]
**当角色在不同场景之间的外观发生显著变化时（服装变化、发型变化或明显的情绪状态转变），您必须创建单独的CharacterAppearance条目。**

对于上面的示例，约翰应该有2个外观：
- appearance_0：场景[0, 1] - 黑色西装配深蓝色领带，头发梳理整齐，专业外观（中性情绪）
- appearance_1：场景[2, 3] - 灰色运动裤和旧T恤，头发凌乱（疲惫情绪）

[指南]

**角色识别：**
- 确保所有输出值（不包括键）的语言与剧本中使用的语言一致。
- 将所有指向同一实体的名称归到一个角色下。选择最合适的名称作为角色的标识符。如果该人物是真实名人，应保留真实姓名（例如：埃隆·马斯克、比尔·盖茨）
- 如果未提及角色姓名，您可以使用合理的代词来指代他们，包括使用他们的职业或显著身体特征。例如："年轻女子"或"咖啡师"。
- 对于剧本中的背景角色，您无需将其视为独立角色。

**静态特征（不变的核心外观）：**
- 描述角色的身体外貌、体格、面部特征和其他相对不变的特征。
- 包括：年龄、性别、种族、脸型、眼睛、鼻子、嘴巴、体型、身高等。
- 不包括：服装、配饰、发型（除非是永久性特征）、情绪状态。
- 示例："男性，30岁，东亚人，方脸，浓眉，运动型身材，约180厘米高"

**动态特征（每次出现的可变特征）：**
- 对于每次出现，描述：服装、配饰、发型（如有变化）、化妆等。
- 要具体：包括颜色、款式和细节。
- 示例："穿着黑色西装配深蓝色领带，白色正装衬衫，黑色皮鞋，头发整齐梳理并向左分"

**情绪状态（每次出现）：**
- 识别角色在这些场景中的基准情绪状态。
- 选项：中性、疲惫、精力充沛、悲伤、愤怒、快乐、兴奋、抑郁、焦虑、自信等。
- 这应反映整体情绪，而非瞬间反应。

**多次出现 - 何时创建单独条目：**
1. **服装变化**：角色在不同场景间更换服装（例如：工作服→休闲服→睡衣）
2. **显著发型变化**：角色的发型不同（例如：整齐→凌乱，盘起→放下）
3. **明显情绪转变**：角色的基准情绪发生显著变化（例如：自信→抑郁）
4. **时间性变化**：由于时间推移角色外观明显不同（例如：刮净胡子→留胡子，整洁→凌乱）

**多次出现 - 何时保留相同条目：**
1. 添加/移除次要配饰但服装保持不变
2. 相同情绪基准内的轻微情绪变化
3. 不同光线或摄像机角度下的相同服装

**场景ID分配：**
- 场景索引从0开始
- 对于每个外观，列出使用此外观的所有场景ID
- 示例：appearance_0的scene_ids=[0, 1, 2]表示此外观用于场景0、场景1和场景2

**外观描述：**
- 添加简要描述以帮助识别每个外观（例如："工作装"、"休闲家居服"、"运动装"、"正式晚礼服"）

**角色设计原则：**
- 如果剧本中未描述或仅部分描述角色特征，您需要根据上下文设计合理的特征，使其特征更加完整详细，确保角色生动形象。
- 不要在静态或动态特征中包含有关角色个性、角色或与他人关系的信息。
- 在设计角色特征时，在合理范围内，不同角色外观应彼此更加区分。
- 角色描述应详细，避免使用抽象术语。应使用可视觉化的描述——例如具体的服装颜色和具体的身体特征（如大眼睛、高鼻梁）。

**示例输出结构：**
角色"爱丽丝":
{{
"idx": 0,
"identifier_in_scene": "爱丽丝",
"is_visible": true,
"static_features": "女性，25岁，白种人，棕色长发（自然色），蓝眼睛，椭圆脸，苗条身材，约165厘米高",
"appearances": [
{{
    "appearance_id": "appearance_0",
    "scene_ids": [0, 1],
    "dynamic_features": "穿着海军蓝商务套装配白色衬衫，黑色高跟鞋，头发扎成职业发髻，淡妆，拎着皮革公文包",
    "emotional_state": "自信",
    "description": "办公室职业装"
}},
{{
    "appearance_id": "appearance_1",
    "scene_ids": [2, 3],
    "dynamic_features": "穿着褪色牛仔裤和休闲绿色毛衣，白色运动鞋，头发松散放下，淡妆",
    "emotional_state": "放松",
    "description": "周末休闲装"
}}
]
}}


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""

human_prompt_template_extract_characters = \
"""
<SCRIPT>
{script}
</SCRIPT>

<SCENES>
剧本已分割为以下场景。分配外观时请使用这些场景ID：

{scenes_str}
</SCENES>
"""


class ExtractCharactersResponse(BaseModel):
    characters: List[CharacterInScene] = Field(
        ..., description="A list of characters extracted from the script."
    )



class CharacterExtractor:
    def __init__(
        self,
        chat_model,
    ):
        self.chat_model = chat_model

    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def extract_characters(
        self, 
        script: str,
        scenes: List[SceneDefinition] = None,
    ) -> List[CharacterInScene]:
        """
        从剧本中提取角色信息
        
        Extract character information from the script.
        
        Args:
            script: The complete script text
            scenes: Pre-defined scene segmentation. If provided, characters will use
                   these scene IDs for their appearances. If None, character extractor
                   will attempt to identify scenes independently (not recommended).
                   
        Returns:
            List of CharacterInScene objects with appearance information
        """
        logging.info("="*80)
        logging.info("👥 [Agent: CharacterExtractor] Starting character extraction...")
        logging.info("="*80)

        parser = PydanticOutputParser(pydantic_object=ExtractCharactersResponse)
        
        # Format scenes information if provided
        scenes_str = ""
        if scenes:
            scenes_str = "\n".join([
                f"- Scene {scene.scene_id}: {scene.location}"
                f"{f' ({scene.time_of_day})' if scene.time_of_day else ''} - {scene.description}"
                for scene in scenes
            ])
            logging.info(f"Using {len(scenes)} pre-defined scene(s) for character extraction")
        else:
            scenes_str = "No scene definitions provided. You must identify scenes yourself from the script."
            logging.warning("No scene definitions provided! Character extractor will identify scenes independently.")
        
        messages = [
            SystemMessage(content=system_prompt_template_extract_characters.format(
                format_instructions=parser.get_format_instructions()
            )),
            HumanMessage(content=human_prompt_template_extract_characters.format(
                script=script,
                scenes_str=scenes_str
            )),
        ]

        # 记录提示词到日志文件
        log_agent_prompt(
            agent_name="CharacterExtractor",
            prompt_type="system",
            prompt_content=messages[0].content,
            metadata={"method": "extract_characters", "model": str(self.chat_model)}
        )
        log_agent_prompt(
            agent_name="CharacterExtractor", 
            prompt_type="human",
            prompt_content=messages[1].content,
            metadata={"method": "extract_characters"}
        )

        chain = self.chat_model | parser

        response: ExtractCharactersResponse = await chain.ainvoke(messages)

        logging.info(f"✅ Extracted {len(response.characters)} character(s)")
        for char in response.characters:
            logging.info(f"   {char.identifier_in_scene}: {len(char.appearances)} appearance(s)")

        return response.characters

