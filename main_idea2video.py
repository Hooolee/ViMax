import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
"""
深夜，城市博物馆。
年轻的侦探江辰站在被打碎的玻璃展柜前，锋利的碎片散落一地，价值连城的"星夜之眼"蓝宝石不翼而飞。馆长惊慌失措，三名保安神色各异。

江辰仔细观察现场。监控显示，晚上十点，神秘黑衣人从天窗闪电般降落，打碎展柜，30秒内完成盗窃并消失。但江辰注意到一个细节：玻璃碎片全部散落在展柜内侧，而非外侧。

"玻璃是从里面被打碎的。"江辰冷静地说。

他转向三名保安。老张，工作二十年的资深保安，手上有新鲜划伤；小李，刚入职三个月的年轻人，神情紧张；王队长，负责当晚巡逻安排，镇定自若。

江辰询问王队长："你今晚为什么改变了巡逻路线？"

王队长脸色微变："因为...东侧有老鼠，我让老张去处理。"

江辰走向老张："手上的伤是怎么回事？"

老张慌乱地解释："今天修门窗时不小心划到的。"

就在这时，江辰注意到监控视频中的一个疑点——"黑衣人"降落时，保安室的灯光闪烁了一下，恰好是小李值班的时间。

"小李，"江辰直视他，"你在十点整做了什么？"

小李额头渗出汗珠："我...我就是正常巡逻..."

江辰突然笑了："不，你在那一刻切断了展厅的压力传感器电源。因为你知道，真正的盗窃不是从天窗，而是从地下通道进入的。"

他走向展柜底部，轻轻敲击，传来空洞的回声。"这是一个配合默契的团伙作案。王队长负责改变巡逻安排，小李负责断电，老张负责从地下通道进入打碎展柜制造从天窗入侵的假象。所谓的监控视频，是提前录制好的画面。"

三人脸色大变。江辰从口袋掏出手机："刚才我已经联系了警方，在地下通道入口发现了新鲜的脚印，和老张的鞋印完全吻合。还有，'星夜之眼'的保险箱钥匙，只有馆长和王队长有——而馆长的钥匙，一直挂在脖子上。"

警笛声响起，真相大白。
"""
user_requirement = \
"""
Create a suspenseful detective story. 3-4 scenes maximum. Each scene should be 4-6 shots, focusing on close-ups of evidence and character expressions to build tension.
"""
style = "Realistic Anime, Detective Conan Style, Cartoon"

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
