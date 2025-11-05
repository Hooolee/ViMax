import logging
from typing import List, Literal
import asyncio
import aiohttp

from interfaces.video_output import VideoOutput
from utils.image import image_path_to_b64


class VideoGeneratorDoubaoSeedanceOfficialAPI:
    """
    Official Doubao (Volcengine Ark) video generation adapter.

    API endpoints:
      - Create task: POST {base_url}/tasks
      - Query task:  GET  {base_url}/tasks/{id}

    The adapter supports:
      - Text-to-video (0 reference images)
      - First-frame image-to-video (1 reference image)
      - First/last-frame image-to-video (2 reference images)

    Returned value is a VideoOutput with fmt="url" that contains the video URL.
    """

    def __init__(
        self,
        api_key: str,
        # Official model name; update as needed
        t2v_model: str = "doubao-seedance-1-0-pro-fast-251015",
        ff2v_model: str = "doubao-seedance-1-0-pro-fast-251015",
        flf2v_model: str = "doubao-seedance-1-0-pro-fast-251015",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations",
    ):
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.ff2v_model = ff2v_model
        self.flf2v_model = flf2v_model
        self.base_url = base_url.rstrip("/")

    async def create_video_generation_task(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: Literal["480p", "720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        duration: int = 5,
        add_watermark: bool = False,
        camera_fixed: bool = False,
    ) -> str:
        """
        Create a task on the official Ark endpoint and return the task ID.
        The Ark API expects the control flags embedded in the text content.
        """
        if len(reference_image_paths) == 0:
            model = self.t2v_model
        elif len(reference_image_paths) == 1:
            model = self.ff2v_model
        elif len(reference_image_paths) == 2:
            model = self.flf2v_model
        else:
            raise ValueError("reference_image_paths must contain 0, 1 or 2 images.")

        logging.info(f"Calling {model} (official Ark) to generate video...")

        # Compose flags per official examples
        flags = [
            f"--resolution {resolution}",
            f"--duration {duration}",
            f"--camerafixed {'true' if camera_fixed else 'false'}",
            f"--watermark {'true' if add_watermark else 'false'}",
        ]

        # Note: official snippet does not include aspect ratio; avoid adding unknown flags

        text_item = {
            "type": "text",
            "text": f"{prompt}  " + " ".join(flags),
        }

        content = [text_item]

        # The official API accepts either public URLs or Data URLs (base64) per docs.
        def to_image_url(path: str) -> str:
            if path.startswith("http://") or path.startswith("https://"):
                return path
            # Convert local file to data URL: data:image/<fmt>;base64,<...>
            try:
                return image_path_to_b64(path)
            except Exception as e:
                logging.warning(f"Failed to base64-encode image '{path}': {e}")
                return None

        image_urls: List[str] = []
        if len(reference_image_paths) >= 1:
            u0 = to_image_url(reference_image_paths[0])
            if u0:
                image_urls.append(u0)
        if len(reference_image_paths) >= 2:
            u1 = to_image_url(reference_image_paths[1])
            if u1:
                image_urls.append(u1)

        # Build candidate payloads with decreasing conditioning: [2 imgs] -> [1 img] -> [0 img]
        def build_payload(urls: List[str]):
            _content = [text_item]
            for u in urls:
                _content.append({"type": "image_url", "image_url": {"url": u}})
            return {"model": model, "content": _content}

        candidate_payloads = []
        if len(image_urls) >= 2:
            candidate_payloads.append(build_payload(image_urls[:2]))
        if len(image_urls) >= 1:
            candidate_payloads.append(build_payload(image_urls[:1]))
        candidate_payloads.append(build_payload([]))

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/tasks"
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    last_err_text = None
                    for attempt_payload in candidate_payloads:
                        async with session.post(url, headers=headers, json=attempt_payload) as resp:
                            if 200 <= resp.status < 300:
                                response_json = await resp.json()
                                task_id = response_json.get("id")
                                if not task_id:
                                    logging.error(f"Unexpected response (missing id): {response_json}")
                                    raise ValueError("Failed to create video task: missing id")
                                logging.info(f"Video generation task created successfully. Task ID: {task_id}")
                                return task_id
                            else:
                                text = await resp.text()
                                last_err_text = f"HTTP {resp.status} body={text}"
                                logging.error(f"Ark task create failed with payload size {len(attempt_payload.get('content', []))}: {last_err_text}")
                                # Try next simplified payload
                                continue
                    # All candidates failed this round; raise to trigger retry sleep
                    raise RuntimeError(f"Ark task create failed for all payload variants. Last error: {last_err_text}")
            except Exception as e:
                logging.error(f"Error creating Ark video task: {e}. Retrying in 1s...")
                await asyncio.sleep(1)

    async def query_video_generation_task(self, task_id: str) -> str:
        """
        Poll the task until completion and return the resulting video URL.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/tasks/{task_id}"

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        resp.raise_for_status()
                        response_json = await resp.json()
            except Exception as e:
                logging.error(f"Error querying Ark video task: {e}. Retrying in 2s...")
                await asyncio.sleep(2)
                continue

            status = response_json.get("status")
            if status == "succeeded":
                content = response_json.get("content")

                def extract_url_from_item(item):
                    if isinstance(item, str):
                        return item if item.startswith("http") else None
                    if not isinstance(item, dict):
                        return None
                    # Common candidates
                    for k in ("video_url", "url", "result_url"):
                        v = item.get(k)
                        if isinstance(v, str) and v.startswith("http"):
                            return v
                        if isinstance(v, dict):
                            u = v.get("url")
                            if isinstance(u, str) and u.startswith("http"):
                                return u
                    # Some APIs put under nested 'content' or 'data'
                    for k in ("content", "data", "output"):
                        v = item.get(k)
                        if isinstance(v, dict):
                            u = extract_url_from_item(v)
                            if u:
                                return u
                        if isinstance(v, list):
                            for it in v:
                                u = extract_url_from_item(it)
                                if u:
                                    return u
                    return None

                video_url = None
                if isinstance(content, list):
                    for it in content:
                        video_url = extract_url_from_item(it)
                        if video_url:
                            break
                else:
                    video_url = extract_url_from_item(content)

                if not video_url:
                    logging.error(f"Succeeded but no video URL found: {response_json}")
                    raise ValueError("Video generation succeeded but no URL returned.")
                logging.info(f"Video generation completed. URL: {video_url}")
                return video_url
            elif status == "failed":
                logging.error(f"Video generation failed. Response: {response_json}")
                raise ValueError("Video generation failed.")
            else:
                logging.info("Video generation in progress. Checking again in 2s...")
                await asyncio.sleep(2)

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: Literal["480p", "720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        duration: int = 5,
    ) -> VideoOutput:
        """High-level helper: create + poll, return VideoOutput(url)."""
        task_id = await self.create_video_generation_task(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            duration=duration,
        )
        video_url = await self.query_video_generation_task(task_id)
        return VideoOutput(fmt="url", ext="mp4", data=video_url)
