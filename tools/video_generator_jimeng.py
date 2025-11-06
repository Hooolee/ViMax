import logging
from typing import List, Literal, Optional
import asyncio
import aiohttp
from interfaces.video_output import VideoOutput
from utils.image import image_path_to_b64


class VideoGeneratorJimeng:
    """
    Video generator for Jimeng API (即梦视频生成)
    Supports three modes:
    - T2V (Text-to-Video): No images
    - I2V (Image-to-Video): Single image as first frame
    - First-Last Frame: Two images as first and last frames
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:5100",
        model: str = "jimeng-video-3.0",
    ):
        """
        Initialize Jimeng video generator.
        
        Args:
            api_key: Session ID for authentication (Bearer token)
            base_url: Base URL of Jimeng API service
            model: Video model to use (jimeng-video-3.0, jimeng-video-3.0-pro, 
                   jimeng-video-2.0, jimeng-video-2.0-pro)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: Literal["720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        duration: Literal[5, 10] = 5,
        response_format: str = "url",
    ) -> VideoOutput:
        """
        Generate a single video using Jimeng API.
        
        Args:
            prompt: Text prompt for video generation
            reference_image_paths: List of 0, 1, or 2 reference images
                - 0 images: Text-to-Video mode
                - 1 image: Image-to-Video mode (first frame)
                - 2 images: First-Last frame mode
            resolution: Video resolution ("720p" or "1080p")
            aspect_ratio: Video aspect ratio (ignored when images are provided)
            duration: Video duration in seconds (5 or 10)
            response_format: Response format ("url" or "b64_json")
            
        Returns:
            VideoOutput containing the video URL or base64 data
        """
        num_images = len(reference_image_paths)
        
        if num_images > 2:
            raise ValueError("reference_image_paths must contain 0, 1, or 2 images.")
        
        # Determine generation mode
        if num_images == 0:
            mode = "T2V (Text-to-Video)"
        elif num_images == 1:
            mode = "I2V (Image-to-Video)"
        else:
            mode = "First-Last Frame"
        
        logging.info(f"Generating video using Jimeng API in {mode} mode with model {self.model}...")
        
        url = f"{self.base_url}/v1/videos/generations"
        
        # Prepare payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "resolution": resolution,
            "duration": duration,
            "response_format": response_format,
        }
        
        # Add ratio only for T2V mode (no images)
        if num_images == 0:
            payload["ratio"] = aspect_ratio
        
        # Add image paths if provided
        if num_images > 0:
            # Convert local paths to base64 data URLs
            file_paths = []
            for image_path in reference_image_paths:
                # Convert to base64 data URL
                b64_url = image_path_to_b64(image_path)
                file_paths.append(b64_url)
            payload["file_paths"] = file_paths
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Make API request with retry logic
        max_retries = 3
        retry_delay = 2
        
        logging.info(f"Sending request to {url}")
        logging.debug(f"Payload: {payload}")
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    # Jimeng API video generation can take 3-15 minutes, set longer timeout
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=1200)) as response:
                        response_text = await response.text()
                        logging.debug(f"Response status: {response.status}, body: {response_text}")
                        
                        if response.status != 200:
                            logging.error(f"API request failed with status {response.status}: {response_text}")
                            if attempt < max_retries - 1:
                                logging.info(f"Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(retry_delay)
                                continue
                            else:
                                raise ValueError(f"Video generation failed after {max_retries} attempts: {response_text}")
                        
                        # Try to parse JSON
                        try:
                            response_json = await response.json()
                        except Exception as json_error:
                            logging.error(f"Failed to parse JSON response: {json_error}")
                            logging.error(f"Response text: {response_text}")
                            raise ValueError(f"Failed to parse API response: {json_error}")
                        
                        logging.debug(f"API Response: {response_json}")
                        
                        # Check if response is valid
                        if response_json is None:
                            error_msg = "API returned empty response"
                            logging.error(error_msg)
                            raise ValueError(error_msg)
                        
                        # Parse response based on format
                        if response_format == "url":
                            # Response format: {"created": timestamp, "data": [{"url": "..."}]}
                            if "data" in response_json and response_json["data"] and len(response_json["data"]) > 0:
                                video_url = response_json["data"][0]["url"]
                                logging.info(f"Video generation completed successfully. Video URL: {video_url}")
                                return VideoOutput(fmt="url", ext="mp4", data=video_url)
                            else:
                                raise ValueError(f"Unexpected response format: {response_json}")
                        else:
                            # b64_json format
                            if "data" in response_json and response_json["data"] and len(response_json["data"]) > 0:
                                b64_data = response_json["data"][0]["b64_json"]
                                logging.info(f"Video generation completed successfully (base64 format)")
                                return VideoOutput(fmt="b64", ext="mp4", data=b64_data)
                            else:
                                raise ValueError(f"Unexpected response format: {response_json}")
                
            except asyncio.TimeoutError:
                logging.error(f"Request timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise ValueError(f"Video generation failed: Request timeout after {max_retries} attempts")
            
            except Exception as e:
                logging.error(f"Error occurred during video generation: {e}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise ValueError(f"Video generation failed after {max_retries} attempts: {str(e)}")
        
        raise ValueError("Video generation failed: Maximum retries exceeded")

    async def generate_videos_batch(
        self,
        prompts: List[str],
        reference_image_paths_list: List[List[str]],
        resolution: Literal["720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        duration: Literal[5, 10] = 5,
        response_format: str = "url",
    ) -> List[VideoOutput]:
        """
        Generate multiple videos in parallel.
        
        Args:
            prompts: List of text prompts
            reference_image_paths_list: List of image path lists (one per prompt)
            resolution: Video resolution
            aspect_ratio: Video aspect ratio
            duration: Video duration in seconds
            response_format: Response format
            
        Returns:
            List of VideoOutput objects
        """
        if len(prompts) != len(reference_image_paths_list):
            raise ValueError("prompts and reference_image_paths_list must have the same length")
        
        tasks = []
        for prompt, ref_images in zip(prompts, reference_image_paths_list):
            task = self.generate_single_video(
                prompt=prompt,
                reference_image_paths=ref_images,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                duration=duration,
                response_format=response_format,
            )
            tasks.append(task)
        
        logging.info(f"Generating {len(tasks)} videos in batch...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        video_outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Failed to generate video {i}: {result}")
                # Return empty VideoOutput for failed generations
                video_outputs.append(VideoOutput(fmt="url", ext="mp4", data=""))
            else:
                video_outputs.append(result)
        
        return video_outputs
