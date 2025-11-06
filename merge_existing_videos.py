"""
合并已生成的场景视频
"""
import os
from pathlib import Path
from moviepy import VideoFileClip, concatenate_videoclips
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

def merge_existing_videos(working_dir: str, output_path: str):
    """
    合并已生成的场景视频
    
    Args:
        working_dir: 工作目录路径
        output_path: 输出视频路径
    """
    # 查找所有已生成的场景视频
    scene_videos = []
    scene_dirs = sorted([d for d in Path(working_dir).iterdir() if d.is_dir() and d.name.startswith('scene_')])
    
    logging.info(f"Found {len(scene_dirs)} scene directories")
    
    for scene_dir in scene_dirs:
        final_video_path = scene_dir / "final_video.mp4"
        if final_video_path.exists():
            logging.info(f"✅ Found video: {final_video_path}")
            scene_videos.append(str(final_video_path))
        else:
            logging.warning(f"⚠️ Missing video for: {scene_dir.name}")
    
    if not scene_videos:
        logging.error("❌ No scene videos found!")
        return
    
    logging.info(f"\n🎬 Merging {len(scene_videos)} videos...")
    
    # 加载所有视频片段
    clips = []
    for video_path in scene_videos:
        try:
            clip = VideoFileClip(video_path)
            clips.append(clip)
            logging.info(f"Loaded: {video_path} (duration: {clip.duration:.2f}s)")
        except Exception as e:
            logging.error(f"Failed to load {video_path}: {e}")
    
    if not clips:
        logging.error("❌ No valid video clips loaded!")
        return
    
    # 合并视频
    logging.info("\n🔄 Concatenating videos...")
    final_clip = concatenate_videoclips(clips, method="compose")
    
    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 导出最终视频
    logging.info(f"\n💾 Writing merged video to: {output_path}")
    final_clip.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=24,
        preset='medium'
    )
    
    # 清理资源
    final_clip.close()
    for clip in clips:
        clip.close()
    
    total_duration = sum(clip.duration for clip in clips)
    logging.info(f"\n✅ Merge completed!")
    logging.info(f"📊 Total scenes: {len(clips)}")
    logging.info(f"⏱️ Total duration: {total_duration:.2f}s")
    logging.info(f"📁 Output file: {output_path}")


if __name__ == "__main__":
    working_dir = ".working_dir/idea2video/detective_mystery"
    output_path = ".working_dir/idea2video/detective_mystery/merged_final_video.mp4"
    
    merge_existing_videos(working_dir, output_path)
