import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
"""资深侦探陈默接手一桩离奇命案，死者是知名企业家张明远，表面看似意外坠楼，但陈默通过敏锐观察发现诸多疑点。在调查过程中，他遭遇重重阻碍，最终通过逻辑推理揭开隐藏在商业竞争背后的谋杀真相。"""
user_requirement = \
"""
创建一个悬疑推理故事。最多3个场景，每个场景4-5个镜头。重点展现侦探陈默的推理过程和紧张氛围。
"""
style = "冷色调，写实风格，电影感"

# 指定输出子目录名称，最终路径会是 .working_dir/<output_subdir>
# 修改这个变量可以生成多个不同的视频而不会覆盖
output_subdir = "detective_mystery"  # 可以改为 "video1", "video2", "sunflower_story" 等

# 是否启用交互模式 (True=每个agent运行后等待用户确认, False=自动运行所有步骤)
interactive_mode = True


async def main():
    if not output_subdir or output_subdir.strip() == "":
        raise ValueError("必须指定 output_subdir！请在脚本中设置一个有效的子目录名称。")
    
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video.yaml",
        output_subdir=output_subdir,
        interactive_mode=interactive_mode
    )
    await pipeline(idea=idea, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
