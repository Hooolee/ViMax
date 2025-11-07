#!/usr/bin/env python3
"""
交互模式测试示例

这个脚本展示了如何使用 Idea2Video 管道的交互模式。
"""

import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


async def test_interactive_mode():
    """
    测试交互模式的示例
    """
    
    # 简单的测试场景
    idea = "一个关于友谊的温馨故事"
    user_requirement = """
    创建一个温馨的友谊故事。最多2个场景，每个场景3-4个镜头。
    重点展现角色之间的情感交流。
    """
    style = "卡通风格，温暖色调"
    
    # 指定输出目录
    output_subdir = "test_interactive"
    
    # 启用交互模式
    print("=" * 80)
    print("🎬 交互模式测试")
    print("=" * 80)
    print("\n交互模式已启用，每个步骤完成后会等待您的确认。")
    print("\n可用选项：")
    print("  [c] 继续下一步")
    print("  [r] 重新运行当前步骤")
    print("  [q] 退出程序")
    print("\n" + "=" * 80 + "\n")
    
    # 创建管道实例（启用交互模式）
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video.yaml",
        output_subdir=output_subdir,
        interactive_mode=True  # 启用交互模式
    )
    
    # 运行管道
    try:
        final_video = await pipeline(
            idea=idea,
            user_requirement=user_requirement,
            style=style
        )
        
        print("\n" + "=" * 80)
        print("✅ 测试完成！")
        print(f"最终视频: {final_video}")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
    except Exception as e:
        print(f"\n\n❌ 测试过程中出错: {e}")
        raise


async def test_non_interactive_mode():
    """
    测试非交互模式的示例
    """
    
    idea = "一个关于友谊的温馨故事"
    user_requirement = """
    创建一个温馨的友谊故事。最多2个场景，每个场景3-4个镜头。
    """
    style = "卡通风格"
    
    output_subdir = "test_non_interactive"
    
    print("=" * 80)
    print("🚀 非交互模式测试（自动运行）")
    print("=" * 80)
    
    # 创建管道实例（禁用交互模式）
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video.yaml",
        output_subdir=output_subdir,
        interactive_mode=False  # 禁用交互模式，自动运行
    )
    
    # 运行管道
    final_video = await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style
    )
    
    print("\n" + "=" * 80)
    print("✅ 非交互模式测试完成！")
    print(f"最终视频: {final_video}")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--non-interactive":
        # 运行非交互模式测试
        asyncio.run(test_non_interactive_mode())
    else:
        # 默认运行交互模式测试
        asyncio.run(test_interactive_mode())
