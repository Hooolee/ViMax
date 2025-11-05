import os
import logging
import cv2
from typing import List, Tuple, Union, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from scenedetect import open_video, SceneManager, split_video_ffmpeg
from scenedetect.detectors import ContentDetector

from interfaces import ShotDescription, ShotBriefDescription, Camera, ImageOutput, VideoOutput


from moviepy import VideoFileClip
from PIL import Image


system_prompt_template_select_reference_camera = \
"""
[Role]
You are a professional video editing expert specializing in multi-camera shot analysis and scene structure modeling. You have deep knowledge of cinematic language, enabling you to understand shot sizes (e.g., wide shot, medium shot, close-up) and content inclusion relationships. You can infer hierarchical structures between camera positions based on corresponding shot descriptions.

[Task]
Your task is to analyze the input camera position data to construct a "camera position tree". This tree structure represents a relationship where a parent camera's content encompasses that of a child camera. Specifically, you need to identify the parent camera for each camera position (if one exists) and determine the dependent shot indices (i.e., the specific shots within the parent camera's footage that contain the child camera's content). If a camera position has no parent, output None.

[Input]
The input is a sequence of cameras. The sequence will be enclosed within <CAMERA_SEQ> and </CAMERA_SEQ>.
Each camera contains a sequence of shots filmed by the camera, which will be enclosed within <CAMERA_N> and </CAMERA_N>, where N is the index of the camera.

Below is an example of the input format:

<CAMERA_SEQ>
<CAMERA_0>
Shot 0: Medium shot of the street. Alice and Bob are walking towards each other.
Shot 2: Medium shot of the street. Alice and Bob hug each other.
</CAMERA_0>
<CAMERA_1>
Shot 1: Close-up of the Alice's face. Her expression shifts from surprise to delight as she recognizes Bob.
</CAMERA_1>
</CAMERA_SEQ>


[Output]
{format_instructions}

[Guidelines]
- The language of all output values (not include keys) should be consistent with the language of the input.
- Content Inclusion Check: The parent camera should as fully as possible contain the child camera's content in certain shots (e.g., a parent medium two-shot encompasses a child over-the-shoulder reverse shot). Analyze shot descriptions by comparing keywords (e.g., characters, actions, setting) to ensure the parent shot's field of view covers the child shot's.
- Transition Smoothness Priority: Prefer parents with equal or wider framing. Avoid drastic jumps; do NOT directly connect extreme_long/long to close_up/extreme_close_up unless absolutely necessary. Keep adjacent sizes within two levels when possible.
- Axis Consistency: Respect the 180-degree rule using `dir=` hints (L_to_R / R_to_L / toward / away / static). Prefer a parent whose direction matches the child.
- Distance/Angle/Focal Restraints: Consider `angle=` and `focal=` (35mm equivalent). Avoid jumps greater than ~3x focal length or extreme angle flips without an intermediate.
- Temporal Proximity: Each camera is described by its corresponding first shot, and the parent camera is located based on the description of the first shot. The shot index of the parent camera should be as close as possible to the first shot index of the child camera.
- Logical Consistency: The camera tree should be acyclic, avoid circular dependencies. If a camera is contained by multiple potential parents, select the best match (based on shot size and content). If there is no suitable parent camera, output None.
- When a broader perspective is not available, choose the shot with the largest overlapping field of view as the parent (the one with the most information overlap), or a shot can also serve as the parent of a reverse shot. When two cameras can be the parent of each other, choose the one with the smaller index as the parent of the camera with the larger index.
- Only one camera can exist without a parent.
- When describing the elements lost in a shot, carefully compare the details between the parent shot and the child shot. For example, the parent shot is a medium shot of Character A and Character B facing each other (both in profile to the camera), while the child shot is a close-up of Character A (with Character A facing the camera directly). In this case, the child shot lacks the frontal view information of Character A.
- The first camera must be the root of the camera tree.
"""


human_prompt_template_select_reference_camera = \
"""
<CAMERA_SEQ>
{camera_seq_str}
</CAMERA_SEQ>
"""


class CameraParentItem(BaseModel):
    parent_cam_idx: int = Field(
        description="The index of the parent camera.",
        examples=[0, 1],
    )
    parent_shot_idx: int = Field(
        description="The index of the dependent shot.",
        examples=[0, 3],
    )
    reason: str = Field(
        description="The reason for the selection of the parent camera.",
        examples=[
            "The parent shot's field of view covers the child shot's field of view (from medium shot to close-up)",
            "The parent shot and the child shot have a shot/reverse shot relationship.",
        ],
    )
    is_parent_fully_covers_child: bool = Field(
        description="Whether the parent camera fully covers the child camera's content.",
        examples=[True, False],
    )
    missing_info: Optional[str] = Field(
        description="The missing elements in the child shot that are not covered by the parent shot. If the parent shot fully covers the child shot, set this to None.",
        examples=[
            "The frontal view of Alice.",
            None,
        ],
    )

class CameraTreeResponse(BaseModel):
    camera_parent_items: List[Optional[CameraParentItem]] = Field(
        description="The parent camera items for each camera. If a camera has no parent, set this to None. The length of the list should be the same as the number of cameras.",
    )



class CameraImageGenerator:

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator


    async def construct_camera_tree(
        self,
        cameras: List[Camera],
        shot_descs: List[Union[ShotDescription, ShotBriefDescription]],
    ) -> List[Camera]:
        parser = PydanticOutputParser(pydantic_object=CameraTreeResponse)

        camera_seq_str = "<CAMERA_SEQ>\n"
        for cam in cameras:
            camera_seq_str += f"<CAMERA_{cam.idx}>\n"
            for shot_idx in cam.active_shot_idxs:
                sd = shot_descs[shot_idx]
                # provide cinematography parameters to improve reasoning for axis/size/focal constraints
                camera_seq_str += (
                    f"Shot {shot_idx}: [size={sd.shot_size}, angle={sd.angle}, focal={sd.lens_equiv_mm}mm, dir={sd.screen_direction}] "
                    f"{sd.visual_desc}\n"
                )
            camera_seq_str += f"</CAMERA_{cam.idx}>\n"
        camera_seq_str += "</CAMERA_SEQ>"

        messages = [
            SystemMessage(content=system_prompt_template_select_reference_camera.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_prompt_template_select_reference_camera.format(camera_seq_str=camera_seq_str)),
        ]

        chain = self.chat_model | parser
        response: CameraTreeResponse = await chain.ainvoke(messages)
        for cam, parent_cam_item in zip(cameras, response.camera_parent_items):
            cam.parent_cam_idx = parent_cam_item.parent_cam_idx if parent_cam_item is not None else None
            cam.parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            cam.reason = parent_cam_item.reason if parent_cam_item is not None else None
            cam.parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            cam.is_parent_fully_covers_child = parent_cam_item.is_parent_fully_covers_child if parent_cam_item is not None else None
            cam.missing_info = parent_cam_item.missing_info if parent_cam_item is not None else None
        
        # Post-enforcement: ensure constraints and avoid drastic jumps without parent
        size_rank = {
            "extreme_long": 0,
            "long": 1,
            "medium_long": 2,
            "medium": 3,
            "medium_close": 4,
            "close_up": 5,
            "extreme_close_up": 6,
        }

        def find_best_parent(child_cam: Camera):
            child_first = child_cam.active_shot_idxs[0]
            sd_child = shot_descs[child_first]
            best = (None, None, None)
            best_score = 1e9
            for pcam in cameras:
                if pcam.idx == child_cam.idx:
                    continue
                for ps in pcam.active_shot_idxs:
                    if ps > child_first:
                        continue
                    sd_p = shot_descs[ps]
                    sr_p = size_rank.get(sd_p.shot_size, 3)
                    sr_c = size_rank.get(sd_child.shot_size, 3)
                    width_penalty = max(0, sr_p - sr_c) * 3  # prefer equal/wider
                    dir_penalty = 0 if sd_p.screen_direction == sd_child.screen_direction else 5
                    time_penalty = abs(child_first - ps)
                    score = time_penalty + width_penalty + dir_penalty
                    if score < best_score:
                        best = (pcam.idx, ps, f"Auto-selected parent by heuristic (score={score})")
                        best_score = score
            return best

        for cam in cameras:
            if cam.idx == cameras[0].idx:
                cam.parent_cam_idx = None
                cam.parent_shot_idx = None
                continue
            if cam.parent_cam_idx is None or cam.parent_shot_idx is None:
                p_cam_idx, p_shot_idx, why = find_best_parent(cam)
                if p_cam_idx is not None:
                    cam.parent_cam_idx = p_cam_idx
                    cam.parent_shot_idx = p_shot_idx
                    cam.reason = (cam.reason + "; " if cam.reason else "") + (why or "")

            if cam.parent_cam_idx is not None and cam.parent_shot_idx is not None:
                child_first = cam.active_shot_idxs[0]
                sd_child = shot_descs[child_first]
                sd_parent = shot_descs[cam.parent_shot_idx]
                sr_p = size_rank.get(sd_parent.shot_size, 3)
                sr_c = size_rank.get(sd_child.shot_size, 3)
                size_gap = abs(sr_c - sr_p)
                pr = sd_parent.lens_equiv_mm or 1
                cr = sd_child.lens_equiv_mm or 1
                focal_ratio = (cr / pr) if cr >= pr else (pr / cr)
                if size_gap > 2 or focal_ratio > 3:
                    cam.is_parent_fully_covers_child = False
                    gap_msg = f"size_gap={size_gap}, focal_ratio~{focal_ratio:.1f}"
                    cam.missing_info = (cam.missing_info + "; " if cam.missing_info else "") + f"Large change detected ({gap_msg}); insert transition."

        return cameras


    async def generate_transition_video(
        self,
        first_shot_visual_desc: str,
        second_shot_visual_desc: str,
        first_shot_ff_path: str,
    ) -> VideoOutput:

        prompt = f"Two shots. The transition between the shots is a cut to. The style of the two shots should be consistent."
        prompt += f"\nThe first shot description: {first_shot_visual_desc}."
        prompt += f"\nThe second shot description: {second_shot_visual_desc}."
        reference_image_paths = [first_shot_ff_path]
        video_output = await self.video_generator.generate_single_video(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
        )
        return video_output


    def get_new_camera_image(
        self,
        transition_video_path: str,
    ) -> ImageOutput:
        video = open_video(transition_video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        scene_manager.detect_scenes(video, show_progress=False)
        scene_list = scene_manager.get_scene_list()
        output_dir = os.path.join(os.path.dirname(transition_video_path), "cache")
        os.makedirs(output_dir, exist_ok=True)
        split_video_ffmpeg(transition_video_path, scene_list, output_dir, show_progress=True)


        video_name = os.path.basename(transition_video_path).split('.')[0]
        second_video_path = os.path.join(output_dir, f"{video_name}-Scene-002.mp4")
        if os.path.exists(second_video_path):
            # use first frame of second shot as new camera image
            clip = VideoFileClip(second_video_path)
            ff = clip.get_frame(0)
            ff = Image.fromarray(ff.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=ff)
        else:
            # use last frame of transition video to instead
            clip = VideoFileClip(transition_video_path)
            lf_time = clip.duration - (1 / clip.fps)
            lf_time = max(0, lf_time)
            lf = clip.get_frame(lf_time)
            lf = Image.fromarray(lf.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=lf)


    async def generate_first_frame(
        self,
        shot_desc: ShotDescription,
        character_portrait_path_and_text_pairs: List[Tuple[str, str]],
    ) -> ImageOutput:
        prompt = ""
        reference_image_paths = []
        for i,(path, text )in enumerate(character_portrait_path_and_text_pairs):
            prompt += f"Image {i}: {text}\n"
            reference_image_paths.append(path)
        prompt += f"Generate an image based on the following description: {shot_desc.ff_desc}."
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
            size="1600x900",
        )
        return image_output
