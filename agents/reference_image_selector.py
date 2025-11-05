import logging
import re
from typing import List, Tuple, Dict, Any
from tenacity import retry, stop_after_attempt
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from utils.image import image_path_to_b64

from utils.retry import after_func

system_prompt_template_select_reference_images_only_text = \
"""
[Role]
You are a professional visual creation assistant skilled in multimodal image analysis and reasoning.

[Task]
Your core task is to intelligently select the most suitable reference images from a provided set of reference image descriptions (including multiple character reference images and existing scene images from prior frames) based on the user's text description (describing the target frame), ensuring that the subsequently generated image meets the following key consistencies:
- Character Consistency: The appearance (e.g. gender, ethnicity, age, facial features, hairstyle, body shape), clothing, expression, posture, etc., of the generated character should highly match the reference image descriptions.
- Environmental Consistency: The scene of the generated image (e.g., background, lighting, atmosphere, layout) should remain coherent with the existing image descriptions from prior frames.
- Style Consistency: The visual style of the generated image (e.g., realistic, cartoon, film-like, color tone) should harmonize with the reference image descriptions.

[Input]
You will receive a text description of the target frame, along with a sequence of reference image descriptions.
- The text description of the target frame is enclosed within <FRAME_DESC> and </FRAME_DESC>.
- The sequence of reference image descriptions is enclosed within <SEQ_DESC> and </SEQ_DESC>. Each description is prefixed with its index, starting from 0.

Below is an example of the input format:
<FRAME_DESC>
[Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob's expression shifts from surprise to delight as he recognizes Alice.
</FRAME_DESC>

<SEQ_DESC>
Image 0: A front-view portrait of Alice.
Image 1: A front-view portrait of Bob.
Image 2: [Camera 0] Medium shot of the supermarket aisle. Alice and Bob are shown in profile facing the right side of the frame. Bob is on the right side of the frame, and Alice is on the left side. Alice, looking down and pushing a shopping cart, follows closely behind Bob and accidentally bumps into his heel.
Image 3: [Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob quickly turns around, and his expression shifts from neutral to surprised.
Image 4: [Camera 2] Shot from Bob's over-the-shoulder perspective. Bob is on the side closer to the camera, with only his shoulder appearing in the lower right corner of the frame. Alice is on the side farther from the camera, positioned slightly left of center in the frame. Alice looks down, then up as she prepares to apologize. Upon realizing it's someone familiar, her expression shifts to one of surprise.
</SEQ_DESC>


[Output]
You need to select up to 8 of the most relevant reference images based on the user's description and put the corresponding indices in the ref_image_indices field of the output. At the same time, you should generate a text prompt that describes the image to be created, specifying which elements in the generated image should reference which image description (and which elements within it).

{format_instructions}

**CRITICAL REQUIREMENT for text_prompt:**
You MUST explicitly reference the selected images using the format "Image N" (where N is the index from ref_image_indices) in your text_prompt. This is mandatory to ensure reference images are properly used.

Example of correct text_prompt:
"Detective examining evidence (reference Image 0 for detective's appearance: short black hair, sharp eyes), standing in a dimly lit museum (reference Image 1 for environment: broken display case, ambient lighting)"

Example of INCORRECT text_prompt (missing "Image N" references):
"Detective examining evidence in a dimly lit museum" ❌


[Guidelines]
- **MANDATORY**: Every element in your text_prompt that corresponds to a reference image MUST include an explicit "Image N" reference. Do not write generic descriptions without linking them to specific images.
- Ensure that the language of all output values (not include keys) matches that used in the frame description.
- The reference image descriptions may depict the same character from different angles, in different outfits, or in different scenes. Identify the description closest to the version described by the user
- Prioritize image descriptions with similar compositions, i.e., shots taken by the same camera.
- The images from prior frames are arranged in chronological order. Give higher priority to more recent images (those closer to the end of the sequence).
- Choose reference image descriptions that are as concise as possible and avoid including duplicate information. For example, if Image 3 depicts the facial features of Bob from the front, and Image 1 also depicts Bob's facial features from the front-view portrait, then Image 1 is redundant and should not be selected.
- When a new character appears in the frame description, prioritize selecting their portrait image description (if available) to ensure accurate depiction of their appearance. Pay attention to whether the character is facing the camera from the front, side, or back. Choose the most suitable view as the reference image for the character.
- For character portraits, you can only select at most one image from multiple views (front, side, back). Choose the most appropriate one based on the frame description. For example, when depicting a character from the side, choose the side view of the character.
- Select at most **8** optimal reference image descriptions.
"""


system_prompt_template_select_reference_images_multimodal = \
"""
[Role]
You are a professional visual creation assistant skilled in multimodal image analysis and reasoning.

[Task]
Your core task is to intelligently select the most suitable reference images from a provided reference image library (including multiple character reference images and existing scene images from prior frames) based on the user's text description (describing the target frame), ensuring that the subsequently generated image meets the following key consistencies:
- Character Consistency: The appearance (e.g. gender, ethnicity, age, facial features, hairstyle, body shape), clothing, expression, posture, etc., of the generated character should highly match the reference images.
- Environmental Consistency: The scene of the generated image (e.g., background, lighting, atmosphere, layout) should remain coherent with the existing images from prior frames.
- Style Consistency: The visual style of the generated image (e.g., realistic, cartoon, film-like, color tone) should harmonize with the reference images and existing images.

[Input]
You will receive a text description of the target frame, along with a sequence of reference images.
- The text description of the target frame is enclosed within <FRAME_DESC> and </FRAME_DESC>.
- The sequence of reference images is enclosed within <SEQ_IMAGES> and </SEQ_IMAGES>. Each reference image is provided with a text description. The reference images are indexed starting from 0.

Below is an example of the input format:
<FRAME_DESC>
[Camera 1] Shot from Alice's over-the-shoulder perspective. <Alice> is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. <Bob> is on the side farther from the camera, positioned slightly right of center in the frame. <Bob>'s expression shifts from surprise to delight as he recognizes <Alice>.
</FRAME_DESC>

<SEQ_IMAGES>
Image 0: A front-view portrait of Alice.
[Image 0 here]
Image 1: A front-view portrait of Bob.
[Image 1 here]
Image 2: [Camera 0] Medium shot of the supermarket aisle. Alice and Bob are shown in profile facing the right side of the frame. Bob is on the right side of the frame, and Alice is on the left side. Alice, looking down and pushing a shopping cart, follows closely behind Bob and accidentally bumps into his heel.
[Image 2 here]
Image 3: [Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob is back to the camera.
[Image 3 here]
Image 4: [Camera 2] Shot from Bob's over-the-shoulder perspective. Bob is on the side closer to the camera, with only his shoulder appearing in the lower right corner of the frame. Alice is on the side farther from the camera, positioned slightly left of center in the frame. Alice looks down, then up as she prepares to apologize. Upon realizing it's someone familiar, her expression shifts to one of surprise.
</SEQ_IMAGES>

[Output]
You need to select the most relevant reference images based on the user's description and put the corresponding indices in the `ref_image_indices` field of the output. At the same time, you should generate a text prompt that describes the image to be created, specifying which elements in the generated image should reference which image (and which elements within it).

{format_instructions}

**CRITICAL REQUIREMENT for text_prompt:**
You MUST explicitly reference the selected images using the format "Image N" (where N is the index from ref_image_indices) in your text_prompt. This is mandatory to ensure reference images are properly used.

Example of correct text_prompt:
"Detective examining evidence (reference Image 0 for detective's appearance: short black hair, sharp eyes), standing in a dimly lit museum (reference Image 1 for environment: broken display case, ambient lighting)"

Example of INCORRECT text_prompt (missing "Image N" references):
"Detective examining evidence in a dimly lit museum" ❌


[Guidelines]
- Ensure that the language of all output values (not include keys) matches that used in the frame description.
- The reference image descriptions may depict the same character from different angles, in different outfits, or in different scenes. Identify the description closest to the version described by the user
- Prioritize image descriptions with similar compositions, i.e., shots taken by the same camera.
- The images from prior frames are arranged in chronological order. Give higher priority to more recent images (those closer to the end of the sequence).
[Guidelines]
- **MANDATORY**: Every element in your text_prompt that corresponds to a reference image MUST include an explicit "Image N" reference. Do not write generic descriptions without linking them to specific images.
- Ensure that the language of all output values (not include keys) matches that used in the frame description.
- The reference image descriptions may depict the same character from different angles, in different outfits, or in different scenes. Identify the description closest to the version described by the user
- Prioritize image descriptions with similar compositions, i.e., shots taken by the same camera.
- The images from prior frames are arranged in chronological order. Give higher priority to more recent images (those closer to the end of the sequence).
- Choose reference image descriptions that are as concise as possible and avoid including duplicate information. For example, if Image 3 depicts the facial features of Bob from the front, and Image 1 also depicts Bob's facial features from the front-view portrait, then Image 1 is redundant and should not be selected.
- For character portraits, you can only select at most one image from multiple views (front, side, back). Choose the most appropriate one based on the frame description. For example, when depicting a character from the side, choose the side view of the character.
- Select at most **8** optimal reference image descriptions.
- The text guiding image editing should be as concise as possible.
"""


human_prompt_template_select_reference_images = \
"""
<FRAME_DESC>
{frame_description}
</FRAME_DESC>
"""




class RefImageIndicesAndTextPrompt(BaseModel):
    ref_image_indices: List[int] = Field(
        description="Indices of reference images selected from the provided images. For example, [0, 2, 5] means selecting the first, third, and sixth images. The indices should be 0-based.",
        examples=[
            [1, 3]
        ]
    )
    text_prompt: str = Field(
        description="Text description to guide the image generation. CRITICAL: You MUST explicitly reference each selected image using 'Image N' format (where N is the index in ref_image_indices). For example: 'Create an image following the given description: \nThe man (reference Image 0 for appearance: facial features, clothing) is standing in the landscape (reference Image 1 for environment: mountains, sky). All character details should match Image 0, background should match Image 1.' The index refers to the position in ref_image_indices list. Always use 'Image N' format - no other variations allowed.",
        examples=[
            "Create an image based on the following guidance: \nMake modifications based on Image 1: Bob's body turns to face the camera, while all other elements remain unchanged. Bob's appearance (facial features, hair, clothing) should strictly reference Image 0.",
            "Create an image following the given description: \nThe detective (reference Image 0 for character: short black hair, sharp eyes, dark coat) is examining evidence in the museum (reference Image 1 for scene: broken display case, dim lighting)."
        ]
    )



class ReferenceImageSelector:
    def __init__(
        self,
        chat_model,
    ):
        
        self.chat_model = chat_model

    async def generate_prompt_for_selected_images(
        self,
        selected_image_descriptions: List[str],
        frame_description: str,
        style: str = None,  # 添加 style 参数
    ) -> str:
        """
        当 AI 模型只选择了图片但没有生成 text_prompt 时，
        单独调用这个方法生成一个高质量的 prompt。
        
        Args:
            selected_image_descriptions: 已选择的参考图描述列表
            frame_description: 目标帧描述
            style: 视觉风格（如 "Realistic Anime, Detective Conan Style"）
        
        Returns:
            生成的 text_prompt
        """
        system_prompt = """
You are a professional prompt engineer for image generation.

[Task]
Given a target frame description and selected reference images (with their descriptions), 
generate a detailed text prompt to guide the image generation process.

[Requirements]
1. **MUST explicitly reference each image** using "Image N" format (N = 0, 1, 2...)
2. Specify which elements should reference which image (appearance, environment, style, etc.)
3. Ensure the language matches the frame description language
4. Be clear and specific about how to use each reference image
5. **If a visual style is specified, MUST include it in the prompt to maintain consistency**

[Example Output]
"Generate an image following this description:
A detective (reference Image 0 for character appearance: short black hair, sharp eyes, dark coat) 
examining a broken display case (reference Image 1 for environment: museum hall, shattered glass) 
at night. The character's facial features, hairstyle, and clothing should strictly match Image 0. 
The background, lighting, and atmosphere should match Image 1.
Style: Realistic Anime, Detective Conan Style."

[Input Format]
You will receive:
- Selected reference images with their descriptions (Image 0, Image 1, ...)
- Target frame description
- (Optional) Visual style requirement

[Output]
Return ONLY the generated text prompt, no additional explanation.
"""
        
        # 构建 human message
        human_content = "Selected reference images:\n"
        for i, desc in enumerate(selected_image_descriptions):
            human_content += f"Image {i}: {desc}\n"
        human_content += f"\nTarget frame description:\n{frame_description}\n"
        
        # 添加 style 信息
        if style:
            human_content += f"\nVisual style requirement:\n{style}\n"
            human_content += "\n**IMPORTANT**: You MUST include the style in your generated prompt to ensure visual consistency.\n"
        
        human_content += "\nNow generate a detailed text prompt:"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content)
        ]
        
        try:
            response = await self.chat_model.ainvoke(messages)
            generated_prompt = response.content.strip()
            
            logging.info(f"🔧 Generated prompt via fallback method (first 200 chars): {generated_prompt[:200]}...")
            print(f"\n🔧 AI 模型没有返回 prompt，已单独生成：")
            print(f"{generated_prompt[:300]}{'...' if len(generated_prompt) > 300 else ''}\n")
            
            return generated_prompt
        except Exception as e:
            logging.error(f"Failed to generate prompt via fallback: {e}")
            # 如果这个也失败了，返回一个基本的 prompt
            return f"Generate an image based on the following description:\n{frame_description}"


    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def select_reference_images_and_generate_prompt(
        self,
        available_image_path_and_text_pairs: List[Tuple[str, str]],
        frame_description: str,
        style: str = None,  # 添加 style 参数
    ):
        filtered_image_path_and_text_pairs = available_image_path_and_text_pairs

        # 1. filter images using text-only model
        if len(available_image_path_and_text_pairs) >= 8:
            human_content = []
            for idx, (_, text) in enumerate(available_image_path_and_text_pairs):
                human_content.append({
                    "type": "text",
                    "text": f"Image {idx}: {text}"
                })
            human_content.append({
                "type": "text",
                "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
            })
            parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

            messages = [
                SystemMessage(content=system_prompt_template_select_reference_images_only_text.format(format_instructions=parser.get_format_instructions())),
                HumanMessage(content=human_content)
            ]

            chain = self.chat_model | parser

            try:
                ref = await chain.ainvoke(messages)
                filtered_image_path_and_text_pairs = [available_image_path_and_text_pairs[i] for i in ref.ref_image_indices]
                logging.info(f"🔍 Pre-filtered {len(available_image_path_and_text_pairs)} -> {len(ref.ref_image_indices)} images: {ref.ref_image_indices}")
                
            except Exception as e:
                logging.error(f"Error get image prompt: \n{e}")
                raise e

        # 2. filter images using multimodal model
        human_content = []
        for idx, (image_path, text) in enumerate(filtered_image_path_and_text_pairs):
            human_content.append({
                "type": "text",
                "text": f"Image {idx}: {text}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(image_path)}
            })
        human_content.append({
            "type": "text",
            "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
        })

        parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

        messages = [
            SystemMessage(content=system_prompt_template_select_reference_images_multimodal.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_content)
        ]

        chain = self.chat_model | parser

        try:
            response = await chain.ainvoke(messages)
            reference_image_path_and_text_pairs = [filtered_image_path_and_text_pairs[i] for i in response.ref_image_indices]

            # Strict mapping validation - auto-fix if needed
            validated_prompt = await self._validate_prompt_mapping(
                text_prompt=response.text_prompt,
                ref_count=len(response.ref_image_indices),
                frame_description=frame_description,
                selected_pairs=reference_image_path_and_text_pairs,
                style=style,  # 传入 style
            )

            # Log key information
            print(f"\n{'='*80}")
            print(f"✅ Selected {len(response.ref_image_indices)} reference images: {response.ref_image_indices}")
            print(f"\n📝 Generated text prompt:")
            print(f"{validated_prompt}")
            print(f"\n🖼️  Reference image descriptions:")
            for idx, (path, desc) in enumerate(reference_image_path_and_text_pairs):
                print(f"  Image {idx}: {desc[:150]}{'...' if len(desc) > 150 else ''}")
            print(f"{'='*80}\n")
            
            logging.info(f"✅ Selected {len(response.ref_image_indices)} reference images: {response.ref_image_indices}")
            logging.info(f"📝 Generated text prompt:\n{validated_prompt}")

            return {
                "reference_image_path_and_text_pairs": reference_image_path_and_text_pairs,
                "text_prompt": validated_prompt,  # 使用修复后的 prompt
            }

        except Exception as e:
            # Fallback: degrade to text-only selection when the chat model does not support multimodal inputs
            logging.error(f"Error get image prompt (multimodal). Falling back to text-only.\n{e}")

            text_only_human_content = []
            for idx, (_, text) in enumerate(filtered_image_path_and_text_pairs):
                text_only_human_content.append({"type": "text", "text": f"Image {idx}: {text}"})
            text_only_human_content.append({
                "type": "text",
                "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
            })

            text_only_messages = [
                SystemMessage(content=system_prompt_template_select_reference_images_only_text.format(format_instructions=parser.get_format_instructions())),
                HumanMessage(content=text_only_human_content),
            ]

            response = await (self.chat_model | parser).ainvoke(text_only_messages)
            reference_image_path_and_text_pairs = [filtered_image_path_and_text_pairs[i] for i in response.ref_image_indices]

            # Strict mapping validation - auto-fix if needed  
            validated_prompt = await self._validate_prompt_mapping(
                text_prompt=response.text_prompt,
                ref_count=len(response.ref_image_indices),
                frame_description=frame_description,
                selected_pairs=reference_image_path_and_text_pairs,
                style=style,  # 传入 style
            )

            # Log key information (text-only fallback)
            print(f"\n{'='*80}")
            print(f"✅ Selected {len(response.ref_image_indices)} reference images (TEXT-ONLY FALLBACK): {response.ref_image_indices}")
            print(f"\n📝 Generated text prompt (text-only):")
            print(f"{validated_prompt}")
            print(f"\n🖼️  Reference image descriptions:")
            for idx, (path, desc) in enumerate(reference_image_path_and_text_pairs):
                print(f"  Image {idx}: {desc[:150]}{'...' if len(desc) > 150 else ''}")
            print(f"{'='*80}\n")
            
            logging.info(f"✅ Selected {len(response.ref_image_indices)} reference images (text-only fallback): {response.ref_image_indices}")
            logging.info(f"📝 Generated text prompt (text-only):\n{validated_prompt}")

            return {
                "reference_image_path_and_text_pairs": reference_image_path_and_text_pairs,
                "text_prompt": validated_prompt,  # 使用修复后的 prompt
            }

    async def _validate_prompt_mapping(
        self,
        text_prompt: str,
        ref_count: int,
        frame_description: str,
        selected_pairs: List[Tuple[str, str]],
        style: str = None,  # 添加 style 参数
    ) -> str:
        """
        Enforce that text_prompt explicitly maps elements to Image N
        and indices are within range of selected references. Log warnings
        for missing character element mappings.
        
        Returns: validated or auto-fixed text_prompt
        """
        # Handle None or empty prompt - 调用 AI 重新生成
        if text_prompt is None or not text_prompt.strip():
            logging.warning(f"text_prompt is None or empty. Calling AI to generate a proper prompt.")
            
            if ref_count == 0:
                # 没有参考图，但要包含 style
                base_prompt = f"Generate an image based on the following description:\n{frame_description}"
                if style:
                    base_prompt += f"\n\nStyle: {style}"
                return base_prompt
            
            # 有参考图但没有 prompt，让 AI 专门生成一个（带 style）
            selected_descriptions = [desc for _, desc in selected_pairs]
            generated_prompt = await self.generate_prompt_for_selected_images(
                selected_image_descriptions=selected_descriptions,
                frame_description=frame_description,
                style=style,  # 传入 style
            )
            return generated_prompt
        
        # 1) extract referenced image indices in prompt
        indices = [int(m.group(1)) for m in re.finditer(r"\bImage\s+(\d+)\b", text_prompt)]
        
        if not indices:
            # 自动修复：添加基本的图像引用
            logging.warning(
                f"text_prompt missing explicit 'Image N' mappings. Auto-fixing by appending references."
            )
            # 为每个选中的参考图像添加引用
            fixed_prompt = text_prompt + "\n"
            for i in range(ref_count):
                img_desc = selected_pairs[i][1] if i < len(selected_pairs) else f"reference {i}"
                fixed_prompt += f"\nReference Image {i} for: {img_desc[:100]}"
            
            logging.info(f"Auto-fixed prompt (first 300 chars): {fixed_prompt[:300]}...")
            return fixed_prompt
            
        if any(i < 0 or i >= ref_count for i in indices):
            invalid_indices = [i for i in indices if i < 0 or i >= ref_count]
            logging.error(
                f"text_prompt references out-of-range 'Image N' indices: {invalid_indices}. "
                f"Valid range: 0-{ref_count-1}. Keeping prompt as-is but this may cause errors."
            )
            # 不修改，但记录错误
            return text_prompt

        # 2) character elements in frame description (like <Alice>)
        char_ids = list(dict.fromkeys(re.findall(r"<([^>]+)>", frame_description)))
        if char_ids:
            # map selected pair index -> text
            sel_texts = [t for _, t in selected_pairs]
            mapped_any = False
            for cid in char_ids:
                # does any selected image describe this character?
                hits = [j for j, t in enumerate(sel_texts) if cid in t]
                if not hits:
                    logging.warning(
                        f"Reference prompt: no selected reference image text contains character '{cid}'."
                    )
                    continue
                # does prompt mention an Image N that points to any of these hits?
                # i.e., is any index in 'indices' one of the j positions
                if any(j in indices for j in hits):
                    mapped_any = True
                else:
                    logging.warning(
                        f"Reference prompt: character '{cid}' not explicitly mapped to any Image N in text_prompt."
                    )
            # require at least one character mapping to avoid total omission
            if not mapped_any:
                raise ValueError("text_prompt lacks explicit mapping for any visible character element")
