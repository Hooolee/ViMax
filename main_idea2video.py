import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
"""A suspenseful detective story where a clever detective unravels a complex mystery through keen observation and deduction."""
user_requirement = \
"""
Create a suspenseful detective story. 3-4 scenes maximum. Each scene should be 4-6 shots, focusing on close-ups of evidence and character expressions to build tension.
"""
style = "anime style, cartoon render, Detective Conan aesthetic"

# 指定输出子目录名称，最终路径会是 .working_dir/<output_subdir>
# 修改这个变量可以生成多个不同的视频而不会覆盖
output_subdir = "detective_mystery"  # 可以改为 "video1", "video2", "sunflower_story" 等


async def main():
    if not output_subdir or output_subdir.strip() == "":
        raise ValueError("必须指定 output_subdir！请在脚本中设置一个有效的子目录名称。")
    
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video.yaml",
        output_subdir=output_subdir
    )
    await pipeline(idea=idea, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
