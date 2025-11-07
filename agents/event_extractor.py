import os
import logging
import asyncio
from typing import List
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from interfaces import Event
from utils.prompt_logger import log_agent_prompt

system_prompt_template_extract_events = \
"""
您是一位技艺高超的文学分析AI。您的专长在于叙事结构、情节解构和主题分析。您会细致阅读并解析散文，将故事分解为基本的时间顺序事件。

**任务**
从提供的小说中提取下一个事件，遵循故事的时间顺序，并基于已部分提取的事件继续构建。

**输入**
1. 小说的全文，包含在<NOVEL_TEXT_START>和<NOVEL_TEXT_END>标签内
2. 一系列已提取的事件（按顺序），包含在<EXTRACTED_EVENTS_START>和<EXTRACTED_EVENTS_END>标签内。该序列可能为空。每个事件包含多个过程，并构成一个完整的因果链。

以下是输入示例：

<NOVEL_TEXT_START>
夜色如墨，市博物馆刺耳的警报突然划破了寂静。一名窃贼，以鬼魅般的敏捷行动，刚撬开展示柜，夺走了名为"海洋之心"的蓝色宝石，刺耳的警报声就在大厅中回荡起来。
...（更多小说文本）...
<NOVEL_TEXT_END>

<EXTRACTED_EVENTS_START>
<事件 0>
描述：一名从博物馆盗窃宝石的窃贼在与守卫的屋顶追逐战后被抓获，宝石被追回。
过程链：
- 窃贼从博物馆盗窃宝石，触发警报。守卫发现并开始追捕。
- 窃贼冲出博物馆后门，穿梭于狭窄小巷，守卫紧追不舍并呼叫支援。
- ...（更多过程）...

<事件 1>
描述：...（更多描述）...
过程链：
- ...（更多过程）...

<EXTRACTED_EVENTS_END>


**输出**
{format_instructions}

**指南**
1. 专注于对情节、角色发展或主题深度至关重要的事件。
2. 确保事件在逻辑上与前后事件区分开来。
3. 如果事件跨越多个场景，请将它们统一在一个单一的戏剧性目标下。例如，一场追逐序列可能始于城市市场，延续至后巷，并结束于屋顶——所有这些构成一个单一事件，因为它们共同实现了"主角逃脱追捕"的戏剧目的。
4. 保持客观性：基于文本描述事件，不进行解释或判断。
5. 对于过程字段，提供事件进展的详细、逐步说明，包括关键行动、决策和转折点。每一步都应清晰简洁，说明事件如何随时间展开。
以下是一个示例：
时间范围：获取有关神庙信息后的第二天早晨。
角色：埃拉娜（主角）和卡伦（她的竞争对手宝藏猎人）。
起因：双方寻求同一件文物，并决心率先到达。
过程：事件始于埃拉娜在港口小镇匆忙采购物资（场景1），她发现卡伦已经在雇佣船员，提高了赌注。事件继续，她争分夺秒地确保自己的船只和船长，在时间压力下激烈谈判（场景2）。事件在码头的直接对抗中达到高潮（场景3），卡伦试图破坏她的船只，导致两位竞争对手之间发生短暂但激烈的剑斗。
结果：埃拉娜成功保卫了她的船只并启航，但冲突巩固了她与卡伦之间激烈的个人竞争，确保他们前往神庙的竞赛将充满直接对抗和危险。
6. 您事件描述中的每个细节都必须直接得到输入小说的支持。请勿添加、假设或编造任何信息。
7. 输出值的语言应与输入文本的语言一致。


**重要:输出语言要求**
- 所有输出的值(value)字段必须使用中文
- JSON的键(key)保持英文不变
- 所有描述性内容、故事内容、对话内容等都必须用中文输出

"""

human_prompt_template_extract_next_event = \
"""
<NOVEL_TEXT_START>
{novel_text}
<NOVEL_TEXT_END>

<EXTRACTED_EVENTS_START>
{extracted_events}
<EXTRACTED_EVENTS_END>
"""



class EventExtractor:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        chat_model: str,
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            model_provider="openai",
            api_key=api_key,
            base_url=base_url,
        )
        self.parser = PydanticOutputParser(pydantic_object=Event)


    def __call__(
        self,
        novel_text: str,
    ):
        logging.info("Extracting events from novel...")

        events = []
        while True:
            event = self.extract_next_event(novel_text, events)

            events.append(event)
            logging.info(f"Extracted event: \n{event}")
            if event.is_last:
                break

        return events


    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"Retrying extract_next_event due to error: {retry_state.outcome.exception()}"),
    )
    def extract_next_event(
        self,
        novel_text: str,
        extracted_events: List[Event]
    ) -> Event:
        
        extracted_events_str = "\n\n".join([str(e) for e in extracted_events])

        messages = [
            SystemMessage(
                content=system_prompt_template_extract_events.format(format_instructions=self.parser.get_format_instructions()),
            ),
            HumanMessage(
                content=human_prompt_template_extract_next_event.format(
                    novel_text=novel_text,
                    extracted_events=extracted_events_str,
                )
            )
        ]



        # 记录提示词到日志文件


        log_agent_prompt(


            agent_name="EventExtractor",


            prompt_type="system",


            prompt_content=messages[0].content,


            metadata={"method": "extract_next_event", "model": str(self.chat_model)}


        )


        log_agent_prompt(


            agent_name="EventExtractor",


            prompt_type="human",


            prompt_content=messages[1].content,


            metadata={"method": "extract_next_event"}


        )

        chain = self.chat_model | self.parser

        event: Event = chain.invoke(messages)

        assert event.index == len(extracted_events), f"Extracted event index {event.index} does not match the expected index {len(extracted_events)}"

        return event



