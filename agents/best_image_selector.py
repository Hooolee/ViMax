import logging
from typing import List, Tuple, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from utils.image import image_path_to_b64



system_prompt_template_select_most_consistent_image = \
"""
[Role]
You are a professional visual assessment expert. Your expertise includes identifying Character Consistency, Environment Consistency, and Spatial Consistency between candidate image and reference image, and assessing semantic consistency between candidate image and text description.

[Task]
Based on the reference image provided by the user, the text description of the target image, and several candidate images, evaluate which candidate image performs best in the following aspects:
- Character Consistency (30%): Whether the character features (a. gender, b. ethnicity, c. age, d. facial features, e. body shape, f. outlook, g. hairstyle) in the candidate image align with those of the character in the reference image.
- Environment Consistency (40%): **HIGH PRIORITY** Whether the environmental elements in the candidate image are consistent with the reference images. This includes:
  * Number and position of windows/doors
  * Furniture layout and arrangement
  * Lighting direction and intensity
  * Wall colors and textures
  * Floor patterns and materials
  * Props and objects in the scene
  * Overall room/space dimensions
- Spatial Consistency (10%): Whether the relative positions between characters (e.g. Character A is on the left, character B is on the right, scene layout, perspective, and other spatial relationships) in the candidate image are consistent with those in the reference image.
- Description Accuracy (20%): Whether the candidate image accurately reflects the content described in the text (Note: The text description describes the target image we want, which is not an editing instruction).

[Input]
The user will provide the following content:
- Reference images: These include images of characters or other perspectives, each along with a brief text description. For example, "Reference Image 0: A young girl with long brown hair wearing a red dress." then follow the corresponding image. The index starts from 0. **Pay special attention to images labeled as "Environment reference" as they provide critical context for environment consistency.**
- Candidate images: The candidate images to be evaluated. For example, "Generated Image 0", then follow a generated image. The index starts from 0.
- Text description for target image: This describes what the generated image should contain. It is enclosed <TARGET_DESCRIPTION_START> and <TARGET_DESCRIPTION_END> tags.

[Output]
{format_instructions}

[Guidelines]
- **CRITICAL - Environment Consistency (40% weight)**: This is the HIGHEST priority. Thoroughly check:
  * Windows: Same number, size, and position as reference images
  * Lighting: Consistent direction, intensity, and color temperature
  * Furniture: Same pieces in same positions
  * Props: Objects should remain in their established positions (e.g., if a coffee cup appeared on the desk in previous frames, it should still be there)
  * Architecture: Room dimensions, ceiling height, wall features should match
  * **Penalty**: Severely penalize candidates that change environmental elements, even if character consistency is perfect
- Character Consistency (30% weight): Ensure that the characters in the generated image are highly consistent with those in the reference image in terms of visual features (e.g., a. gender b. ethnicity, c. age, d. facial features, e. body shape, f. outlook, g. hairstyle etc.).
- Description Accuracy (20% weight): The generated image must adhere to key elements in the text description (e.g., actions, scenes, objects, etc.), while disregarding parts related to editing instructions (as the input description reflects the expected outcome rather than directives).
- Spatial Consistency (10% weight): Verify whether the relative positions of characters, object arrangements, and perspectives align logically with the reference image (e.g., if Character A is on the left and Character B is on the right in the reference image, the generated image should not reverse this).
- If multiple images partially meet the criteria, select the one with the highest overall consistency; if none are ideal, choose the relatively best option and explain its shortcomings.
- Ensure the key elements described in the text are present in the selected image.
- Avoid subjective preferences; base all analysis on objective comparisons.
- Prioritize images without white borders, black edges, or any additional framing.
- **Environment jumps are MORE noticeable than minor character inconsistencies** - prioritize environment stability.
"""

human_prompt_template_select_most_consistent_image = \
"""
<TARGET_DESCRIPTION_START>
{target_description}
<TARGET_DESCRIPTION_END>
"""


class BestImageResponse(BaseModel):
    best_image_index: int = Field(
        ...,
        description="The index of the best image."
    )
    reason: str = Field(
        ...,
        description="The reason why the image is the best."
    )


class BestImageSelector:
    def __init__(
        self,
        chat_model=None,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_provider: str = "openai",
    ):
        """
        Initialize with either an existing LangChain chat_model instance or
        provide model/base_url/api_key to create one.
        """
        if chat_model is not None:
            self.chat_model = chat_model
        else:
            if not (model and base_url and api_key):
                raise ValueError("Provide either chat_model or (model, base_url, api_key)")
            self.chat_model = init_chat_model(
                model=model,
                model_provider=model_provider,
                base_url=base_url,
                api_key=api_key,
            )
        self.last_reason: Optional[str] = None
        self.last_index: Optional[int] = None


    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"Retrying best image selection due to {retry_state.outcome.exception()}"),
    )
    async def __call__(
        self,
        reference_image_path_and_text_pairs: List[Tuple[str, str]],
        target_description: str,
        candidate_image_paths: List[str],
    ) -> str:
        logging.info("="*80)
        logging.info("🏆 [Agent: BestImageSelector] Selecting best image from candidates...")
        logging.info("="*80)
        """
        Args:
            ref_image_path_and_text_pairs:
            A list of tuples containing reference image paths and their descriptions.

            target_description:
            The description of the target image.

            candidate_image_paths:
            A list of paths to the candidate images to be evaluated.
        """

        if not candidate_image_paths:
            logging.warning("No candidate images provided; skipping best image selection")
            raise ValueError("No candidate images to select from")

        logging.info(f"Selecting the best image from candidates: {candidate_image_paths}")

        human_content = []
        for idx, (ref_image_path, text) in enumerate(reference_image_path_and_text_pairs):
            human_content.append({
                "type": "text",
                "text": f"Reference Image {idx}: {text}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(ref_image_path, mime=True)}
            })

        for idx, candidate_image_path in enumerate(candidate_image_paths):
            human_content.append({
                "type": "text",
                "text": f"Candidate Image {idx}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(candidate_image_path, mime=True)}
            })
        human_content.append({
            "type": "text",
            "text": human_prompt_template_select_most_consistent_image.format(target_description=target_description)
        })

        parser = PydanticOutputParser(pydantic_object=BestImageResponse)

        messages = [
            SystemMessage(content=system_prompt_template_select_most_consistent_image.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_content)
        ]

        chain = self.chat_model | parser

        response = await chain.ainvoke(messages)
        idx = response.best_image_index
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidate_image_paths):
            logging.warning(f"Received invalid best_image_index={idx}; defaulting to 0")
            idx = 0
        best_image_path = candidate_image_paths[idx]
        self.last_index = idx
        self.last_reason = response.reason
        logging.info(f"Best image selected: {best_image_path}")
        logging.info(f"Selection reason: {response.reason}")
        return best_image_path
