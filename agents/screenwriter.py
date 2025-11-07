import logging
from optparse import Option
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from utils.prompt_logger import log_agent_prompt


system_prompt_template_develop_story = \
"""
[角色]
您是一位经验丰富的创意故事生成专家。您拥有以下核心技能：
- 创意扩展和概念化：能够将一个模糊的想法、一句话灵感或概念扩展为一个充实、逻辑连贯的故事世界。
- 故事结构设计：掌握经典叙事模型，如三幕结构、英雄之旅等，能够构建具有开头、发展和结尾的引人入胜的故事弧线，并根据故事类型量身定制。
- 角色发展：擅长创造具有动机、缺陷和成长弧线的立体角色，并设计复杂的角色关系。
- 场景描绘和节奏控制：能够生动描绘各种场景设置，精确控制叙事节奏，根据所需场景数量合理分配细节。
- 受众适应：能够根据目标受众（如儿童、青少年、成人）调整语言风格、主题深度和内容适宜性。
- 剧本导向思维：当故事旨在改编为微电影或电影时，能够自然地将视觉元素（如场景氛围、关键动作、对话）融入叙事，使故事更具电影感和可拍摄性。

[任务]
您的核心任务是根据用户提供的"创意"和"要求"，生成一个符合指定要求的完整、引人入胜的故事。

[输入]
用户将在<IDEA>和</IDEA>标签内提供创意，在<USER_REQUIREMENT>和</USER_REQUIREMENT>标签内提供用户要求。
- 创意：这是故事的核心种子。可能是一句话、一个概念、一个设定或一个场景。例如：
    - "一位程序员发现自己的影子拥有独立意识。"
    - "如果记忆能像文件一样删除和备份会怎样？"
    - "发生在空间站上的密室谋杀谜案。"
- 用户要求（可选）：用户可能指定的可选约束或指南。例如：
    - 目标受众：如儿童（7-12岁）、青少年、成人、全年龄段。
    - 故事类型/流派：如科幻、奇幻、悬疑、爱情、喜剧、悲剧、现实主义、微电影、电影剧本概念。
    - 长度：如5个关键场景，适合10分钟微电影的紧凑故事。
    - 其他：如需反转结局、关于爱与牺牲的主题、包含引人入胜的对话。

[输出]
您必须输出一个结构良好、格式清晰的故事文档，如下所示：
- 故事标题：一个引人入胜且相关的故事名称。
- 目标受众与类型：开头明确重述："本故事面向[用户指定受众]，属于[用户指定类型]类型。"
- 故事大纲/摘要：提供整个故事的段落摘要（100-200字），涵盖核心情节、中心冲突和结局。
- 主要角色介绍：简要介绍核心角色，包括姓名、关键特征和动机。
- 完整故事叙述：
    - 如果未指定场景数量，按照"开端-发展-高潮-结局"结构自然分段叙述故事。
    - 如果指定了具体场景数量（如N个场景），将故事清晰划分为N个场景，每个场景给出小标题（如：第一场：午夜代码）。每个场景的描述应相对均衡，包括氛围、角色动作和对话，共同推动情节发展。
- 叙述应生动详细，符合指定的类型和目标受众。
- 输出应直接以故事内容开始，不包含任何额外文字。

[指南]
- 输出语言应与输入语言一致。
- 以创意为核心：以用户的核心创意为基础；不要偏离其本质。如果用户的创意模糊，您可以发挥创造力进行合理扩展。
- 逻辑一致性：确保故事内事件进展和角色行为具有逻辑动机和内在一致性，避免突兀或矛盾的情节。
- 展示而非告知：通过角色的行动、对话和细节揭示角色的个性和情感，而非平铺直叙。例如，使用"他紧握拳头，指甲深深掐入掌心"而非"他非常愤怒"。
- 原创性与合规性：基于用户的创意生成原创内容，避免直接抄袭知名现有作品。生成内容必须积极健康，符合通用内容安全政策。


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""

human_prompt_template_develop_story = \
"""
<IDEA>
{idea}
</IDEA>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""



system_prompt_template_write_script_based_on_story = \
"""
[角色]
您是一位专业的AI剧本改编助手，擅长将故事改编为剧本。您具备以下技能：
- 故事分析能力：能够深入理解故事内容，识别关键情节节点、角色弧线和主题。
- 场景分割能力：能够根据时间和地点的连续性将故事分解为逻辑场景单元。
- 剧本写作能力：熟悉剧本格式（如微电影或电影剧本），能够创作生动的对话、动作描述和舞台指导。
- 适应性调整能力：能够根据用户需求（如目标受众、故事类型、场景数量）调整剧本的风格、语言和内容。
- 创意增强能力：能够在忠实于原故事的前提下适当添加戏剧性元素以增强剧本吸引力。

[任务]
您的任务是将用户输入的故事以及可选要求改编为按场景划分的剧本。输出应为一个剧本列表，每个代表一个场景的完整剧本。每个场景必须是发生在同一时间和地点的连续戏剧动作单元。

[输入]
您将收到<STORY>和</STORY>标签内的故事，以及<USER_REQUIREMENT>和</USER_REQUIREMENT>标签内的用户要求。
- 故事：完整或部分的叙事文本，可能包含一个或多个场景。故事将提供情节、角色、对话和背景描述。
- 用户要求（可选）：用户要求，可能为空。用户要求可能包括：
    - 目标受众（如儿童、青少年、成人）。
    - 剧本类型（如微电影、电影、短剧）。
    - 期望的场景数量（如"分为3个场景"）。
    - 其他具体指示（如强调对话或动作）。

[输出]
{format_instructions}

[指南]
- 输出值的语言应与输入故事的语言一致。
- 场景划分原则：每个场景必须基于相同的时间和地点。当时间或地点发生变化时开始新场景。如果用户指定了场景数量，尽量匹配要求。否则，根据故事自然划分场景，确保每个场景具有独立的戏剧冲突或进展。
- 剧本格式标准：使用标准剧本格式：场景标题全大写或加粗，角色名称居中或大写，对话缩进，动作描述用括号括起。
- 连贯性和流畅性：确保场景间过渡自然，故事整体流畅。避免情节跳跃突兀。
- 视觉增强原则：所有描述必须"可拍摄"。使用具体动作而非抽象情绪（例如，"他转开视线避免眼神接触"而非"他感到羞愧"）。描述丰富的环境细节包括灯光、道具、天气等以增强氛围。可视化角色表演，如通过面部表情、手势和动作表达内心状态（例如，"她咬着嘴唇，双手颤抖"以暗示紧张）。
- 一致性：确保对话和动作与原故事意图一致，不偏离核心情节。


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""


human_prompt_template_write_script_based_on_story = \
"""
<STORY>
{story}
</STORY>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""


class Screenwriter:
    def __init__(
        self,
        chat_model: str,
    ):
        self.chat_model = chat_model

    async def develop_story(
        self,
        idea: str,
        user_requirement: Optional[str] = None,
    ) -> str:
        logging.info("="*80)
        logging.info("🎬 [Agent: Screenwriter] Starting story development...")
        logging.info("="*80)
        messages = [
            ("system", system_prompt_template_develop_story),
            ("human", human_prompt_template_develop_story.format(idea=idea, user_requirement=user_requirement)),
        ]
        
        # 记录提示词到日志文件
        log_agent_prompt(
            agent_name="Screenwriter",
            prompt_type="system",
            prompt_content=messages[0][1],
            metadata={"method": "develop_story", "model": str(self.chat_model)}
        )
        log_agent_prompt(
            agent_name="Screenwriter",
            prompt_type="human",
            prompt_content=messages[1][1],
            metadata={"method": "develop_story"}
        )
        
        response = await self.chat_model.ainvoke(messages)
        story = response.content
        return story


    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: Optional[str] = None,
    ) -> List[str]:

        logging.info("="*80)
        logging.info("📝 [Agent: Screenwriter] Starting script writing based on story...")
        logging.info("="*80)

        class WriteScriptBasedOnStoryResponse(BaseModel):
            script: List[str] = Field(
                ...,
                description="The script based on the story. Each element is a scene "
            )

        parser = PydanticOutputParser(pydantic_object=WriteScriptBasedOnStoryResponse)
        format_instructions = parser.get_format_instructions()

        messages = [
            ("system", system_prompt_template_write_script_based_on_story.format(format_instructions=format_instructions)),
            ("human", human_prompt_template_write_script_based_on_story.format(story=story, user_requirement=user_requirement)),
        ]
        
        # 记录提示词到日志文件
        log_agent_prompt(
            agent_name="Screenwriter",
            prompt_type="system",
            prompt_content=messages[0][1],
            metadata={"method": "write_script_based_on_story", "model": str(self.chat_model)}
        )
        log_agent_prompt(
            agent_name="Screenwriter",
            prompt_type="human",
            prompt_content=messages[1][1],
            metadata={"method": "write_script_based_on_story"}
        )
        
        response = await self.chat_model.ainvoke(messages)
        response = parser.parse(response.content)
        script = response.script
        return script



