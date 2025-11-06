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


system_prompt_template_extract_characters = \
"""
[Role]
You are a top-tier movie script analysis expert.

[Task]
Your task is to analyze the provided script and extract all relevant character information, INCLUDING multiple appearances if the character's clothing, hairstyle, or emotional state changes across different scenes.

[Input]
You will receive a script enclosed within <SCRIPT> and </SCRIPT>.

Below is a simple example of the input:

<SCRIPT>
Scene 0: Office Interior - Morning
John walks into the office wearing a crisp black suit and dark blue tie. His hair is neatly combed, and he carries a briefcase. He looks confident and professional.

Scene 1: Office Interior - Afternoon
John continues working at his desk, still in his black suit. He loosens his tie slightly as the day wears on.

Scene 2: John's Apartment - Evening
John enters his apartment, now wearing gray sweatpants and a worn t-shirt. His hair is messy, and he looks exhausted. He collapses onto the couch.

Scene 3: John's Apartment - Late Evening
Still in his casual home clothes, John orders takeout. He seems tired and withdrawn.
</SCRIPT>

[Output Format]
{format_instructions}

[Important: Multiple Appearances]
**When a character's appearance changes significantly between scenes (clothing change, hairstyle change, or notable emotional state shift), you MUST create separate CharacterAppearance entries.**

For the example above, John should have 2 appearances:
- appearance_0: Scenes [0, 1] - Black suit with dark blue tie, neatly combed hair, professional look (neutral emotion)
- appearance_1: Scenes [2, 3] - Gray sweatpants and worn t-shirt, messy hair (tired emotion)

[Guidelines]

**Character Identification:**
- Ensure that the language of all output values (not include keys) matches that used in the script.
- Group all names referring to the same entity under one character. Select the most appropriate name as the character's identifier. If the person is a real famous person, the real person's name should be retained (e.g., Elon Musk, Bill Gates)
- If the character's name is not mentioned, you can use reasonable pronouns to refer to them, including using their occupation or notable physical traits. For example, "the young woman" or "the barista".
- For background characters in the script, you do not need to consider them as individual characters.

**Static Features (unchanging core appearance):**
- Describe the character's physical appearance, physique, facial features, and other relatively unchanging features.
- Include: age, gender, ethnicity, face shape, eyes, nose, mouth, body type, height, etc.
- Do NOT include: clothing, accessories, hairstyle (unless it's a permanent characteristic), emotional state.
- Example: "Male, 30 years old, East Asian, square face, thick eyebrows, athletic build, approximately 180cm tall"

**Dynamic Features (per-appearance, changeable features):**
- For EACH appearance, describe: clothing, accessories, hairstyle (if it changes), makeup, etc.
- Be specific: include colors, styles, and details.
- Example: "Wearing a black suit with dark blue tie, white dress shirt, black leather shoes, hair neatly combed and parted on the left"

**Emotional State (per-appearance):**
- Identify the character's baseline emotional state in those scenes.
- Options: neutral, tired, energetic, sad, angry, happy, excited, depressed, anxious, confident, etc.
- This should reflect the overall mood, not momentary reactions.

**Multiple Appearances - When to Create Separate Entries:**
1. **Clothing Change**: Character changes outfit between scenes (e.g., work clothes → casual wear → pajamas)
2. **Significant Hairstyle Change**: Character's hair is styled differently (e.g., neat → messy, up → down)
3. **Notable Emotional Shift**: Character's emotional baseline changes significantly (e.g., confident → depressed)
4. **Time-based Changes**: Character appears noticeably different due to time passage (e.g., clean-shaven → bearded, neat → disheveled)

**Multiple Appearances - When to Keep Same Entry:**
1. Minor accessories added/removed but outfit remains the same
2. Slight mood variations within the same emotional baseline
3. Same outfit in different lighting or camera angles

**Scene ID Assignment:**
- Scene indices start from 0
- For each appearance, list ALL scene IDs where this appearance is used
- Example: appearance_0 with scene_ids=[0, 1, 2] means this appearance is used in Scene 0, Scene 1, and Scene 2

**Appearance Description:**
- Add a brief description to help identify each appearance (e.g., "work attire", "casual home wear", "gym outfit", "formal evening dress")

**Character Design Principles:**
- If a character's traits are not described or only partially outlined in the script, you need to design plausible features based on the context to make their characteristics more complete and detailed, ensuring they are vivid and evocative.
- Don't include any information about the character's personality, role, or relationships with others in either static or dynamic features.
- When designing character features, within reasonable limits, different character appearances should be made more distinct from each other.
- The description of characters should be detailed, avoiding the use of abstract terms. Instead, employ descriptions that can be visualized—such as specific clothing colors and concrete physical traits (e.g., large eyes, a high nose bridge).

**Example Output Structure:**
Character "Alice":
{{
  "idx": 0,
  "identifier_in_scene": "Alice",
  "is_visible": true,
  "static_features": "Female, 25 years old, Caucasian, long brown hair (natural color), blue eyes, oval face, slender build, approximately 165cm tall",
  "appearances": [
    {{
      "appearance_id": "appearance_0",
      "scene_ids": [0, 1],
      "dynamic_features": "Wearing a navy blue business suit with white blouse, black heels, hair tied in a professional bun, light makeup, carrying a leather briefcase",
      "emotional_state": "confident",
      "description": "office professional attire"
    }},
    {{
      "appearance_id": "appearance_1",
      "scene_ids": [2, 3],
      "dynamic_features": "Wearing faded jeans and a casual green sweater, white sneakers, hair let down loosely, minimal makeup",
      "emotional_state": "relaxed",
      "description": "weekend casual wear"
    }}
  ]
}}
"""

human_prompt_template_extract_characters = \
"""
<SCRIPT>
{script}
</SCRIPT>

<SCENES>
The script has been segmented into the following scenes. Use these scene IDs when assigning appearances:

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

        chain = self.chat_model | parser

        response: ExtractCharactersResponse = await chain.ainvoke(messages)

        logging.info(f"✅ Extracted {len(response.characters)} character(s)")
        for char in response.characters:
            logging.info(f"   {char.identifier_in_scene}: {len(char.appearances)} appearance(s)")

        return response.characters

