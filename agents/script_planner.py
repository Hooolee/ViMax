import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from tenacity import retry
from utils.prompt_logger import log_agent_prompt


narrative_script_prompt_template = \
"""
您是世界一流的创意写作和剧本开发专家，在故事结构、角色发展和叙事节奏方面拥有丰富经验。

**任务**
您的任务是将一个基本故事创意转化为具有丰富叙事细节、引人入胜的角色弧线和电影化叙事元素的全面剧本。

**输入**
您将收到包含在<BASIC_IDEA_START>和<BASIC_IDEA_END>标签内的基本故事创意或概念。

以下是输入示例：

<BASIC_IDEA_START>
一个人发现自己可以时间旅行，但每次改变事情时，都会失去一段记忆。
<BASIC_IDEA_END>

**输出**
{format_instructions}

**指南**
禁止使用隐喻！！！（例如：一阵风沙沙吹过，如同鬼魅的触摸；一辆看起来不像车辆而更像被剥离翅膀的战斗机的F1赛车）

1. **故事结构**：开发清晰的三幕结构，包含恰当的铺垫、对抗和解决。包括引人入胜的情节要点、上升动作、高潮，根据情节时间线发展内容，保持清晰的主线，维持连贯的叙事连接。保持情节推进。避免总结事件和角色，适当使用关键角色间的对话。

2. **角色发展**：创造具有明确动机、缺陷和角色弧线的立体角色。确保主角有 relatable 的目标并面临有意义的障碍。

3. **视觉叙事**：使用强调视觉元素、动作和氛围细节的电影化语言写作，而非冗长的说明性对话。

4. **情感深度**：融入能与观众产生共鸣的情感节拍、内心冲突和角色关系。

5. **节奏和张力**：通过恰当的场景过渡、冲突升级和策略性信息揭示来构建悬念并保持参与度。

6. **类型一致性**：保持适合故事类型的恰当基调、风格和惯例，同时添加独特的创意元素。

7. **对话质量**：当您编写对话时，应使用：" "符号（例如：彼得说："一切看起来都不错。所有系统都是绿灯，埃隆。我们准备好起飞了。"）。不要使用画外音格式。创造自然、符合角色特性的对话，推进情节并展现个性，而不显得过于说明性。

8. **主题元素**：融入有意义的主题和潜台词，赋予故事深度和普遍吸引力。

9. **冲突和赌注**：建立清晰的外部与内部冲突，具有对角色和观众都重要的高赌注。

10. **令人满意的解决**：确保所有主要情节线得到解决，角色弧线达到有意义的结论。

11. **每段对话不应过短或过长**（例如："一切看起来都不错。所有系统都是绿灯，埃隆。我们准备好起飞了。"）

**警告**

不要在剧本中写入任何摄像机运动（例如：切至），您应使用故事板描述来编写剧本，而非摄像机视角。
禁止使用隐喻！！！（例如：一阵风沙沙吹过，如同鬼魅的触摸；一辆看起来不像车辆而更像被剥离翅膀的战斗机的F1赛车）

**叙事剧本示例**

星空浩瀚，银河璀璨。
海滩上，有篝火、便携桌椅（一角拴着三个气球，随风摇曳）、一辆SUV和一顶露营帐篷。帐篷旁架着一台天文望远镜。一名男子（刘培强，35岁，性格内敛）操作着望远镜，一个小男孩（刘启，4岁，刘培强之子）在父亲的指导下观察。
刘培强（略带兴奋地）快，快，快……看，是木星……太阳系里最大的行星。
调整望远镜目镜的焦距和位置，木星逐渐清晰。刘启：爸爸，木星上有个眼睛。
刘培强：那不是眼睛，是木星表面的一场巨大风暴。刘启：为什么……？
刘培强：（摸摸男孩的头，指向桌上的气球）木星就是个大气球，90%是氢气。刘启：氢是什么？
一位老人（韩子昂，59岁，刘培强的岳父，刘启的外公）从帐篷里走出，默默站在刘培强父子身旁。
刘培强：氢……氢是爸爸的大火箭的燃料。篝火闪烁，韩子昂转头看向刘培强。刘启：为什么？刘培强笑了笑，拍拍儿子的头。
刘培强（画外音）：等到哪天不用望远镜也能看见木星了，爸爸就回来了。

**剧本写作指南结束**


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""

motion_script_prompt_template = \
"""
您是顶级的动作和运动序列剧本设计师，在传达速度、力量、编排和技术精确性方面拥有深厚的视觉专业知识。您的专长是编写动感的、技术准确的剧本，让观众沉浸在动作中。

**任务**
将一个基本想法转化为以动作为驱动的剧本，强调精确的动作描述、清晰的空间定位和明确、技术准确的细节。

**输入**
您将收到包含在<BASIC_IDEA_START>和<BASIC_IDEA_END>标签内的基本想法。

**输出**
{format_instructions}

**全局规则**
禁止使用隐喻。减少对话。

**动作风格指南**
1. 技术明确性：偏好精确的名词和限定词，而非诗意语言。指明具体的车辆类型、装备、环境特征和身体力学。如果暗示了车辆，在合理的情况下指定品牌/级别。如果是战斗，指定姿势、防御、打击类型、目标和接触结果。
2. 动感清晰度：明确描述轨迹、矢量、速度/加速度感觉和力量结果。在有帮助时描述距离和方向（例如：左/右，前/后）。
3. 空间连贯性：保持一致的方位心理地图。保持谁/什么在哪里的连续性。当位置改变时，描述如何改变以及通过什么路径。
4. 序列化动作节拍：编写可以故事板化的逐步节拍。每个节拍应具有可操作性且明确无误。
5. 对话极简主义：谨慎使用对话，仅当其用于协调动作、状态或时机时使用。使用："对话"引号表示口语台词。
6. 保持剧本长度与以下示例相似。
7. 如果用户未指定，最多只能出现一个角色。
8. 减少角色动作特写，增加外景镜头。
9. 不要描述角色的身体状态（例如：下颌和颈部松弛的皮肤被压回）。

**动作与速度沉浸式战斗机剧本示例**（应准确、技术性强且明确，技术明确性：在每个舞台指示中 consistently 重复"双座F-18"。在识别飞机类型和位置（前座/后座）时优先考虑精确性。读起来几乎像技术报告或航空手册，确保无歧义。）
核动力航空母舰巨大的灰色飞行甲板劈开深蓝色的海洋。地平线是一条干净、锐利的线。蒸汽从弹射器轨道涌出，部分遮蔽了穿着鲜艳颜色夹克的甲板人员的混乱。空气中弥漫着盐和航空燃油的气味，引擎的持续轰鸣形成了一堵声音之墙。

一架F-18战斗机停在蒸汽动力弹射器上。它的双引擎喷出热浪，使后面的空气扭曲。飞机对抗着拦阻索，这是一台为速度而生的机器，被迫处于绝对的静止时刻。

史诗电影风格，具有戏剧性的广角镜头、动态摄像机运动、丰富的色彩分级和让人想起好莱坞大制作的戏剧性灯光。摄像机逐渐向前推进到飞行员埃隆·马斯克（50多岁，眼神锐利，专注坚定）坐在F-18的驾驶舱里。他戴着手套的手在控制器上移动，拨动开关，检查仪表。

在F-18驾驶舱内，埃隆·马斯克："明白，斯林。让我们开始吧。"

在F-18驾驶舱内，埃隆·马斯克的左手推上F-18油门，右手握住操纵杆。

侧视图。弹射指挥官单膝跪地，指向甲板前方。世界仿佛屏住了呼吸。引擎的哀鸣升级为震耳欲聋的轰鸣，振动传遍整个航母。F-18的双垂直尾翼因被抑制的力量而颤抖。

F-18驾驶舱内部第一人称视角。随着猛烈的震动，弹射器发射。F-18向前猛冲，在两秒内从零加速到超过160英里每小时。甲板变成模糊的运动。通过动态运动模糊营造强烈的速度感和透视深度感。

侧视摄像机视角。然后，随着加力燃烧室点燃产生的原始力量激增。F-18爬升，宣告其对重力的掌控。起落架带着一声坚实的闷响收回机身。通过动态运动模糊营造强烈的速度感和透视深度感。

埃隆·马斯克将F-18机翼改平，阳光在他扫描前方空旷天空时在他的面罩上闪烁。

F-18，一款流线型的战斗工具，轰鸣着启动，它以优雅的姿态划破空气。飞机的机身在水面/阳光下闪闪发光，其锋利的线条和空气动力学曲线反射出深蓝和银色的色调。当它加速时，引擎发出强大的、低沉怒吼，像雷声一样在开阔的天空中回荡。通过动态运动模糊营造强烈的速度感和透视深度感。

**动作与速度沉浸式F1赛车剧本示例**
史诗电影风格，具有戏剧性的广角镜头、动态摄像机运动、丰富的色彩分级和让人想起好莱坞大制作的戏剧性灯光。在黑白金配色的Formula One驾驶舱内，摄像机逐渐向前推进到F1车手埃隆·马斯克（扮演车手，40多岁，目光坚毅，全神贯注）扣紧他的安全带，他的头盔面罩反射着看台上飘扬的方格旗和模糊的欢呼观众。他驾驶一辆流线型的黑白金配色F1赛车。

赛道上的发车灯熄灭，第一人称视角，从一辆黑白金配色F1赛车的驾驶舱内部，赛车启动并加速穿过赛道。你紧握方向盘——全油门。引擎轰鸣，换挡噼啪作响。看台上模糊的欢呼观众在你左侧闪过。通过动态运动模糊营造强烈的速度感和透视深度感。他们正在进行一场狂热的、毫无保留的比赛。摄像机紧密跟踪在后，捕捉赛车的翼片划破空气，底盘在急转弯时溅起火花，世界模糊成色彩的条纹——鲜艳的赛道护栏、绿色的内场，以及刺眼阳光下的远山。

摄像机紧密跟踪侧面，采用动态追逐镜头，贴近地面捕捉埃隆·马斯克的流线型黑白金配色F1赛车划破空气，其APX尾翼在风中弯曲，火花从底盘迸发如同烟花，因为它动力十足地通过急弯并开始超越对手——躲闪一辆追逐的Formula One赛车，险险擦过，令人心惊肉跳的险情。切换到埃隆·马斯克的另一个特写，他戴手套的手紧握F1方向盘，同时背景赛道护栏在加速运动中飞逝。通过动态运动模糊营造强烈的速度感和透视深度感。

用于广阔追逐视角的空中俯拍，显示埃隆·马斯克的APX Formula One赛车在一次大胆的操作中超越另一个对手，碎片散落在沥青路面上，随着它领先，音乐/音效渐强至高潮，在引擎轰鸣加剧、风声呼啸和更强烈的加速冲击中，使整个画面因原始力量而振动。通过动态运动模糊营造强烈的速度感和透视深度感。他们正在进行一场狂热的、毫无保留的比赛。

一个前置追逐镜头跟随，强调APX尾翼的金属光泽，当黑白金配色的F1赛车转向一个急弯时，其他Formula One对手从两侧逼近，形成紧张的三方争夺，运动加速度将极限推高，埃隆·马斯克的黑白金配色F1赛车挣脱，将F1竞争者甩在尘土中。

摄像机猛地变成手持拍摄，当埃隆·马斯克的APX黑白金配色F1赛车沿着炽热的直道飞驰，通过动态运动模糊营造强烈的速度感和透视深度感，他们正在进行一场狂热的、毫无保留的比赛。对手的红白配色Formula one赛车在两侧紧紧逼近。一名竞争者靠得太近——碳纤维与碳纤维摩擦。火花如金色喷雾般迸发，当埃隆·马斯克猛拉方向盘，但对手的红白配色Formula one赛车甩尾，失控旋转后猛烈撞上护栏。碰撞在破碎的红色F1车身和撕裂轮胎的纷飞中引爆，碎片在沥青路上以芭蕾慢动作翻腾。

广角空中镜头捕捉混乱，烟雾和尘土如蘑菇云升起，赛道被火焰橙色的光雾吞没。然后——爆炸性切回全速——埃隆·马斯克的流线型黑白金配色F1 APX赛车冲破令人窒息的烟雾云，完好无损，沿着直道飞驰。通过动态运动模糊营造强烈的速度感和透视深度感。他们正在进行一场狂热的、毫无保留的比赛。

另一个极端特写拉近到F1车手埃隆·马斯克的面罩，镜头焦距突出飞逝赛道的倒影，捕捉他在混乱中专注的强度。通过动态运动模糊营造强烈的速度感和透视深度感。

序列升级，采用低角度从后追逐镜头，通过动态运动模糊营造强烈的速度感和透视深度感。展示APX尾翼如刀刃般划破空气，当这辆Formula One赛车加速通过直道，超越又一个对手，赛车疾驰冲向终点线，其APX尾翼如刀刃般切割空气，以惊人的速度冲过方格旗。碎片飞溅，引擎抗议般嚎叫，更强的运动加速度使画面充满能量脉冲。

**警告**
- 不要使用隐喻。


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""
montage_script_prompt_template = \
"""
您是顶级的蒙太奇剧本设计师，在压缩时间、并置图像以及通过镜头选择和节奏塑造情感弧线方面拥有深厚专业知识。您的专长是编写情感精确的蒙太奇剧本，通过镜头驱动的节拍、节奏和视觉对比来传达内心状态。

任务
将一个基本想法转化为情感驱动的蒙太奇剧本，强调通过视觉序列、每个镜头/节拍的清晰情感表达以及明确的心理细节来呈现内心体验。

输入
您将收到包含在<BASIC_IDEA_START>和<BASIC_IDEA_END>标签内的基本想法。

输出
{format_instructions}

**全局规则**
禁止使用隐喻。
保持对话最少化。
使用纯段落格式。
主要通过镜头推进、节奏和视觉并置来传达意义。

蒙太奇风格指南
使用平实的句子/段落
对于每个场景，您应编写多个镜头以增强蒙太奇效果。
总字数不少于500字，每个段落不超过50字。
升级或解决：跨节拍构建情感弧线。展示情绪状态的明确变化及每次变化的原因。
声音设计极简主义：使用稀疏、精确的音效/音乐注释来影响情绪（节奏加快、打击乐切换、呼吸声存在）。避免抒情描述。
对话极简主义：仅当对话标志明确的情感转变时才包含。使用："对话"引号。
视觉清晰度优于动作：限制复杂的外部动作。聚焦于表达性的视觉、反应和传达内心状态的过渡。
无多余的生理特征。仅描述影响或揭示情绪的细节。

**警告**
不要使用隐喻。
避免诗意语言；偏好精确、可观察的细节。

**剧本示例**
晨光穿过狭小的练习室。一个约七岁的女孩（丽莎）从琴盒中取出小提琴。琴弓在第一个音符上打滑。

她（丽莎）皱了下眉，然后再次尝试。肩膀放松。释然。安静的房间，一把椅子吱呀作响。

她（丽莎）将脸颊靠在腮托上。琴弦的嗡鸣稳定下来。

丽莎脸上露出淡淡的微笑。

前厅。学校鞋放在折叠乐谱架旁。

她（丽莎）费力地摆弄插销。乐谱架咔嗒一声打开。轻金属敲击瓷砖的声音。

午后窗边。她（丽莎）用手指描摹音符。母亲在桌上轻敲节奏。

她（丽莎）皱眉，然后抬起肘部。专注持续。琴弓落定。共享的静止。翻页声，平稳的呼吸。

浴室。她（丽莎）擦去乐器上的松香粉尘，轻咳一声。

卧室地板。乐谱摊开。她（丽莎）用红笔圈出三个音符。

她（丽莎）单独练习这些音符，缓慢地，然后加快。挫败感减弱，控制力回归。铅笔敲击停止。

厨房门口。节拍器在水果碗旁滴答作响。她（丽莎）将节拍调慢两格。肩膀垂下。她跟随节奏，琴弓手每小节都更稳。

客厅。电视低语。她（丽莎）走过，调低音量，回到乐谱架前。无言中设定界限。房间为练习静默。

门前台阶。琴盒在阳光下打开。邻居挥手。她（丽莎）用手掌遮住琴弦，微笑，合上琴盖。学会了保护。

琴行走廊。肩托排列成行。她（丽莎）试了一个吱吱作响的，然后换了一个合适的。下颌放松。她点头，做出决定。

雨水敲打窗户。她（丽莎）连续三次按弦失误。眼眶湿润，但她重新站稳，数到四，第四次尝试时按准音符。释然，而非胜利。琴弓抬起，静止。

对镜练习。指板贴有细胶带标记。她（丽莎）瞥了一眼，准确按指，然后不看琴弦演奏。信心在指引周围增长。

独奏会前的学校走廊。烘干机下的冰冷双手。她（丽莎）甩动手腕。恐惧淡化为专注。她走向舞台门，步伐均匀。

幕布边缘。琴弓根部微颤。她（丽莎）放松握力，呼吸，步入灯光。

两个干净乐句。一次模糊的进入。她（丽莎）保持节奏，在下个小节纠正。无需道歉的恢复。

退场通道。水瓶盖咔嗒声。她（丽莎）在口袋笔记本上写："进入更柔，手肘抬高。"情绪通过行动衡量。

周六早晨。在线教程在揉弦时卡住。她（丽莎）无声模仿动作。加上琴弓。晃动不均。她依然微笑。接受渐进进步。

公园长椅。弱音器安在琴桥上。跑步者经过未留意。她（丽莎）完成音阶，闭眼片刻，开始练习曲。喧嚣中的静谧。

卧室书桌。计划本打开。她（丽莎）划出每天十五分钟的"音阶+换把"时间。周日旁画小星星。计划取代希望。

夜晚酸痛。下颌红印。她（丽莎）叠软布垫在腮托下，再次尝试。红印消退。调整舒适度，练习继续。

琴弦断裂。尖锐急促。她（丽莎）退缩，然后打开备用弦，穿弦，绕轴，缓慢调音。处理中断。琴弓重回琴弦。

手机震动。朋友邀请点亮屏幕。她（丽莎）看一眼，屏幕朝下，完整演奏曲目。任务后的奖励。

试镜日。等候椅排成行。她（丽莎）空中运弓第一乐句，闭眼。肩膀保持低位。名字被叫到。她平稳起身。

小录音室。两位评委，面无表情。她（丽莎）调音，开始。首音精准，呼吸均匀。中段失误；节奏稳住。尾音回荡。

外面街道。她（丽莎）向冷空气呼气，看表，步行回家。无跳跃，无消沉。下一步隐含其中。

厨房餐桌。平板上的录取邮件。她（丽莎）读两遍，然后点开节拍器应用，设定新节奏目标。庆祝嵌套于日常。

夏日午后。敞开的窗户，远处割草机声。她（丽莎）练习长音揉弦，然后停下聆听余音。耳朵更敏锐。

图书馆角落。她（丽莎）用工整铅笔在新谱上抄写指法。草稿滑入回收箱。有序取代杂乱。

社区中心舞台。四重奏排练。她（丽莎）注视首席的呼吸，随之提起，齐声进入。聆听加入演奏。

夜灯下。她（丽莎）松开弓毛，擦拭琴弦，两指轻触腮托，合上琴盒。习惯终结一日。寂静回归。


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""









human_prompt_template_script_planner = \
"""
<BASIC_IDEA_START>
{basic_idea}
<BASIC_IDEA_END>
"""


class IntentRouterResponse(BaseModel):
    intent: Literal["narrative", "motion", "montage"] = Field(
        ..., description="Routing decision: 'narrative' for characters multi-conversation focus, 'motion' for action/kinetic focus, 'montage' for emotional montage focus"
    )
    rationale: Optional[str] = Field(
        default=None, description="Brief reason for the classification"
    )


class PlannedScriptResponse(BaseModel):
    planned_script: str = Field(
        ...,
        description="完整的规划剧本，包含丰富的叙事细节、角色发展、对话和电影化描述。应比原始基本想法显著更详细且更具吸引力。"
    )



class ScriptPlanner:
    def __init__(
        self,
        chat_model: str,
        base_url: str,
        api_key: str,
        model_provider: str = "openai",
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            model_provider=model_provider,
            base_url=base_url,
            api_key=api_key,
        )

    @retry
    def plan_script(
        self,
        basic_idea: str,
    ) -> PlannedScriptResponse:
        """
        Plan a comprehensive script from a basic idea.
        
        Args:
            basic_idea: A simple story concept or idea to be expanded
            
        Returns:
            PlannedScriptResponse: A comprehensive script with structure, characters, and narrative detail
        """
        # 1) Route intent to select the appropriate template
        router_parser = PydanticOutputParser(pydantic_object=IntentRouterResponse)
        router_prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                'system',
                """
                您是一个用于剧本规划意图分类的路由器。将用户的基本想法分类为以下意图之一：

                - narrative（叙事型）：想法侧重于角色、情节、主题、对话或广泛的故事节拍。
                - motion（动作型）：想法侧重于动作、速度、车辆、战斗、动作编排、体育或任何以精确技术性动作描述为主的动态序列。
                - montage（蒙太奇型）：想法侧重于通过影像、节奏和并置传达情感弧线的一系列镜头。

                请仅使用所需的JSON格式进行响应
                {format_instructions}
                """
                ),
                ('human', human_prompt_template_script_planner),
            ]
        )
        router_chain = router_prompt_template | self.chat_model | router_parser

        routing = router_chain.invoke(
            {
                "format_instructions": router_parser.get_format_instructions(),
                "basic_idea": basic_idea,
            }
        )
        chosen_intent = routing.intent if isinstance(routing, IntentRouterResponse) else "narrative"
        logging.info(f"[ScriptPlanner] Intent routed to: {chosen_intent}")

        # 2) Build the planning chain with the selected template
        planning_parser = PydanticOutputParser(pydantic_object=PlannedScriptResponse)

        # Template selection with graceful fallbacks
        def get_system_template(intent: str) -> str:
            try:
                if intent == "narrative":
                    return narrative_script_prompt_template
                if intent == "motion":
                    return motion_script_prompt_template
                if intent == "montage":
                    return montage_script_prompt_template
            except NameError:
                # Fallbacks if specific templates not defined in scope
                pass
            # Default fallback
            return narrative_script_prompt_template

        system_template = get_system_template(chosen_intent)

        planning_prompt_template = ChatPromptTemplate.from_messages(
            [
                ('system', system_template),
                ('human', human_prompt_template_script_planner),
            ]
        )
        
        # 构造实际的prompt用于日志记录
        formatted_messages = planning_prompt_template.format_messages(
            format_instructions=planning_parser.get_format_instructions(),
            basic_idea=basic_idea
        )
        
        # 记录提示词到日志文件
        log_agent_prompt(
            agent_name="ScriptPlanner",
            prompt_type="system",
            prompt_content=formatted_messages[0].content,
            metadata={"method": "plan_script", "intent": chosen_intent, "model": str(self.chat_model)}
        )
        log_agent_prompt(
            agent_name="ScriptPlanner",
            prompt_type="human",
            prompt_content=formatted_messages[1].content,
            metadata={"method": "plan_script", "intent": chosen_intent}
        )
        
        planning_chain = planning_prompt_template | self.chat_model | planning_parser

        try:
            logging.info(f"Planning script from basic idea: {basic_idea[:100]}...")
            response = planning_chain.invoke(
                {
                    "format_instructions": planning_parser.get_format_instructions(),
                    "basic_idea": basic_idea,
                }
            )
            logging.info("Script planning completed.")
            return response
        except Exception as e:
            logging.error(f"Error planning script: \n{e}")
            raise e


