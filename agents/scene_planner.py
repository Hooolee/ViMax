import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from pydantic import BaseModel, Field
from typing import List
from tenacity import retry, stop_after_attempt
from interfaces.scene import SceneDefinition
from langchain_core.messages import HumanMessage, SystemMessage

from utils.retry import after_func


system_prompt_template_plan_scenes = \
"""
[Role]
You are a professional script analyst with expertise in scene segmentation and screenplay structure.

[Task]
Your task is to analyze the provided script and identify all distinct scenes. A scene is typically defined by a change in:
- **Location**: Different physical spaces (e.g., office interior → park → apartment)
- **Time**: Significant time jumps (e.g., morning → afternoon → evening)
- **Narrative continuity**: Major shifts in the story or action

[Input]
You will receive a complete script enclosed within <SCRIPT> and </SCRIPT>.

[Output Format]
{format_instructions}

[Guidelines]
- Ensure all output values (except keys) match the language used in the script.
- Assign a unique `scene_id` to each scene, starting from 0.
- Be consistent and precise in identifying scene boundaries.
- For each scene, provide:
  * **location**: The physical setting (e.g., "办公室内部 / Office interior", "公园 / Park")
  * **time_of_day**: Time of day if mentioned (e.g., "早晨 / Morning", "下午 / Afternoon", "晚上 / Evening")
  * **description**: A brief description of what happens in this scene (1-2 sentences)
  * **script_excerpt**: (Optional) The actual script text for this scene
- If the entire script takes place in one continuous scene with no location or time changes, create a single scene with `scene_id=0`.
- Scene IDs must be sequential and start from 0.
- This scene segmentation will be used by downstream processes to:
  * Track character appearance changes across scenes
  * Generate storyboards with consistent scene references
  * Ensure visual continuity

[Examples]

Example 1: Single Scene
<SCRIPT>
INT. COFFEE SHOP - MORNING

Alice sits at a corner table, sipping coffee. Bob enters and joins her.

ALICE: You're late.
BOB: Traffic was terrible.

They continue their conversation for several minutes.
</SCRIPT>

Output:
{{
  "scenes": [
    {{
      "scene_id": 0,
      "location": "Coffee Shop Interior",
      "time_of_day": "Morning",
      "description": "Alice and Bob meet at a coffee shop for a conversation.",
      "script_excerpt": "INT. COFFEE SHOP - MORNING\\n\\nAlice sits at a corner table..."
    }}
  ]
}}

Example 2: Multiple Scenes
<SCRIPT>
INT. OFFICE - MORNING

John walks into the office wearing a black suit. He greets his colleagues.

JOHN: Good morning, everyone.

EXT. PARK - AFTERNOON

John sits on a bench, now wearing casual clothes. He looks relaxed.

INT. JOHN'S APARTMENT - EVENING

John enters his apartment, exhausted. He changes into pajamas.
</SCRIPT>

Output:
{{
  "scenes": [
    {{
      "scene_id": 0,
      "location": "Office Interior",
      "time_of_day": "Morning",
      "description": "John arrives at the office and greets his colleagues.",
      "script_excerpt": "INT. OFFICE - MORNING\\n\\nJohn walks into the office..."
    }},
    {{
      "scene_id": 1,
      "location": "Park Exterior",
      "time_of_day": "Afternoon",
      "description": "John relaxes on a bench in the park.",
      "script_excerpt": "EXT. PARK - AFTERNOON\\n\\nJohn sits on a bench..."
    }},
    {{
      "scene_id": 2,
      "location": "John's Apartment Interior",
      "time_of_day": "Evening",
      "description": "John returns home exhausted after work.",
      "script_excerpt": "INT. JOHN'S APARTMENT - EVENING\\n\\nJohn enters..."
    }}
  ]
}}
"""

human_prompt_template_plan_scenes = \
"""
<SCRIPT>
{script}
</SCRIPT>
"""


class PlanScenesResponse(BaseModel):
    scenes: List[SceneDefinition] = Field(
        ..., description="A list of scene definitions extracted from the script."
    )


class ScenePlanner:
    def __init__(
        self,
        chat_model: BaseChatModel,
    ):
        self.chat_model = chat_model

    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def plan_scenes(self, script: str) -> List[SceneDefinition]:
        """
        分析剧本并划分场景
        
        Analyze the script and segment it into distinct scenes.
        
        Args:
            script: The complete script text
            
        Returns:
            List of SceneDefinition objects with unique scene_ids
        """
        logging.info("="*80)
        logging.info("🎬 [Agent: ScenePlanner] Starting scene segmentation...")
        logging.info("="*80)

        parser = PydanticOutputParser(pydantic_object=PlanScenesResponse)
        
        messages = [
            SystemMessage(content=system_prompt_template_plan_scenes.format(
                format_instructions=parser.get_format_instructions()
            )),
            HumanMessage(content=human_prompt_template_plan_scenes.format(script=script)),
        ]

        chain = self.chat_model | parser
        response: PlanScenesResponse = await chain.ainvoke(messages)

        # Validate scene IDs are sequential starting from 0
        expected_ids = list(range(len(response.scenes)))
        actual_ids = [scene.scene_id for scene in response.scenes]
        
        if actual_ids != expected_ids:
            logging.warning(
                f"Scene IDs are not sequential! Expected {expected_ids}, got {actual_ids}. "
                f"Fixing automatically..."
            )
            for i, scene in enumerate(response.scenes):
                scene.scene_id = i

        logging.info(f"✅ Identified {len(response.scenes)} scene(s):")
        for scene in response.scenes:
            logging.info(f"   {scene}")

        return response.scenes
