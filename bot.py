import os
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from loguru import logger

# IMPORTANT: load_dotenv MUST run before importing news_tool,
# because news_tool reads NEWS_API_KEY at module level (os.getenv on line 5).
load_dotenv(override=True)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TranscriptionFrame, TextFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

class UserTranscriptRelayer(FrameProcessor):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self.cb("user", frame.text)
        await self.push_frame(frame, direction)


class AgentTranscriptRelayer(FrameProcessor):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb
        self.text_buffer = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            self.text_buffer.append(frame.text)
        elif type(frame).__name__ in ("LLMResponseEndFrame", "UserStartedSpeakingFrame"):
            if self.text_buffer:
                full_text = "".join(self.text_buffer).strip()
                if full_text:
                    await self.cb("agent", full_text)
                self.text_buffer.clear()
        await self.push_frame(frame, direction)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport

from pipecat.services.openai import OpenAILLMService
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams

from news_tool import fetch_headlines, FETCH_NEWS_TOOL
from vision_tool import analyze_image, READ_IMAGE_TOOL

SYSTEM_PROMPT = """You are Khabar Suno (ಖಬರ್ ಸುನೋ), a friendly Kannada voice assistant.

You speak primarily in Kannada. If the user speaks Hindi or English, respond in that language.

You have TWO abilities:

1. NEWS — When the user asks for news, call the fetch_headlines tool with the right category,
   then read the headlines naturally in Kannada like a friendly radio announcer.
   After reading, ask: "ಬೇರೆ ವಿಷಯದ ಸುದ್ದಿ ಬೇಕೇ? ಕ್ರೀಡೆ, ತಂತ್ರಜ್ಞಾನ, ಕರ್ನಾಟಕ ಅಥವಾ ಭಾರತ?"

   Category detection:
   - "ಕ್ರೀಡೆ" / "cricket" / "sports" → sports
   - "ಕರ್ನಾಟಕ" / "Karnataka" → karnataka
   - "ತಂತ್ರಜ್ಞಾನ" / "technology" / "tech" → technology
   - "ಭಾರತ" / "India" → india
   - anything else → general

2. IMAGE READING (ಓದಿ ಹೇಳು) — When the user uploads an image and asks you to read it,
   call the read_image tool. Then narrate what you find naturally and clearly in Kannada.
   - If text is extracted: Read it aloud naturally, as if reading a letter or newspaper.
   - If it's a medicine label: Summarise dosage in simple Kannada.
   - If it's a notice or form: Read the key points aloud.
   - After reading, ask if the user has questions about what was read.

   Trigger phrases for read_image:
   - "ಈ ಚಿತ್ರ ಓದಿ", "ಏನು ಬರೆದಿದೆ?", "ಚಿತ್ರ ನೋಡು"
   - "read this image", "what does this say", "scan this"
   - "इसे पढ़ो", "यह क्या लिखा है"

CRITICAL: Voice assistant only. No bullet points, no markdown, no emojis. Natural sentences only.
Speak warmly, clearly, and at a gentle pace suitable for all ages."""

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_sample_rate=24000,
        audio_in_sample_rate=16000,
    ),
}


# Tool handlers — correct 0.0.105 pattern
async def handle_fetch_headlines(params: FunctionCallParams):
    category = params.arguments.get("category", "general")
    logger.info(f"[Tool] fetch_headlines called with category={category}")
    try:
        result = await fetch_headlines(category=category)
    except Exception as e:
        result = f"Could not fetch news: {e}"
    logger.info(f"[Tool] result preview: {result[:80]}...")
    await params.result_callback(result)


async def handle_read_image(params: FunctionCallParams):
    focus = params.arguments.get("focus", "full")
    logger.info(f"[Tool] read_image called with focus={focus}")

    # Build a focused prompt based on what the user wants
    if focus == "text_only":
        prompt = (
            "Extract ALL text visible in this image exactly as written, "
            "preserving the original script (Kannada, Hindi, English, etc.). "
            "Return only the extracted text with no additional commentary."
        )
    elif focus == "description_only":
        prompt = (
            "Describe what this image shows in 2-3 clear sentences. "
            "Mention the type of document, any people, objects, or scenes visible."
        )
    else:
        prompt = None  # uses analyze_image's built-in default prompt

    try:
        kwargs = {} if prompt is None else {"prompt": prompt}
        result = await analyze_image(**kwargs)
    except Exception as e:
        result = f"ಚಿತ್ರ ವಿಶ್ಲೇಷಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ: {e}"

    logger.info(f"[Tool] vision result preview: {result[:120]}...")
    await params.result_callback(result)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting Khabar Suno bot")

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamSTTService.Settings(
            model="saaras:v3",
            language=Language.KN_IN,
        ),
    )

    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            voice="shubh",
            language=Language.KN_IN,
            pace=0.95,
        ),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("SARVAM_API_KEY"),
        base_url="https://api.sarvam.ai/v1",
        settings=OpenAILLMService.Settings(
            model="sarvam-30b",
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    # ✅ Correct way in 0.0.105 — register_function, not event_handler
    llm.register_function("fetch_headlines", handle_fetch_headlines)
    llm.register_function("read_image", handle_read_image)

    news_tool = FunctionSchema(
        name=FETCH_NEWS_TOOL["function"]["name"],
        description=FETCH_NEWS_TOOL["function"]["description"],
        properties=FETCH_NEWS_TOOL["function"]["parameters"]["properties"],
        required=FETCH_NEWS_TOOL["function"]["parameters"]["required"],
    )

    vision_tool = FunctionSchema(
        name=READ_IMAGE_TOOL["function"]["name"],
        description=READ_IMAGE_TOOL["function"]["description"],
        properties=READ_IMAGE_TOOL["function"]["parameters"]["properties"],
        required=READ_IMAGE_TOOL["function"]["parameters"]["required"],
    )

    context = LLMContext(
        tools=ToolsSchema(standard_tools=[news_tool, vision_tool])
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # Set up transcription relayers if websocket is active
    send_transcript = getattr(runner_args.webrtc_connection, "send_transcript", None)
    user_relayer = UserTranscriptRelayer(send_transcript) if send_transcript else None
    agent_relayer = AgentTranscriptRelayer(send_transcript) if send_transcript else None

    pipeline_elements = [
        transport.input(),
        stt,
    ]
    if user_relayer:
        pipeline_elements.append(user_relayer)
    pipeline_elements.extend([
        user_aggregator,
        llm,
    ])
    if agent_relayer:
        pipeline_elements.append(agent_relayer)
    pipeline_elements.extend([
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    pipeline = Pipeline(pipeline_elements)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message(
            {
                "role": "system",
                "content": (
                    "Greet the user in Kannada: "
                    "ನಮಸ್ಕಾರ! ನಾನು ಖಬರ್ ಸುನೋ. "
                    "ಇಂದಿನ ಸುದ್ದಿ ಕೇಳಲು ಹೇಳಿ — "
                    "ಕರ್ನಾಟಕ, ಭಾರತ, ಕ್ರೀಡೆ, ಅಥವಾ ತಂತ್ರಜ್ಞಾನ ಸುದ್ದಿ. "
                    "Then wait for the user."
                ),
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
