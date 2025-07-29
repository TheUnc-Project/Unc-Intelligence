import json
from typing import List, Dict, Any
from openai import AsyncOpenAI
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLM:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM service with OpenAI configuration.

        Args:
            config: Configuration dictionary containing OpenAI settings
        """
        if not config:
            raise ValueError("Configuration is required")

        self.api_key = config.get("OPENAI_API_KEY")
        self.model = config.get("OPENAI_MODEL", "gpt-4.1")
        self.temperature = float(config.get("OPENAI_TEMPERATURE", "0.1"))
        self.max_tokens = int(config.get("OPENAI_MAX_TOKENS", "1000"))

        if not self.api_key:
            logger.error("Missing OpenAI API key")
            raise ValueError("OPENAI_API_KEY is required in configuration")

        self.client = AsyncOpenAI(api_key=self.api_key)

        self.system_prompt = """
You are an AI-powered message interpretation engine for a WhatsApp-based customer feedback analyzer.

You will receive a chronological list of messages exchanged between a user and the system. Each message has:
- type: either "text" or "media"
- text or url: depending on the type
- direction: either "inbound" (from user) or "outbound" (from system)

Your task is to analyze the entire conversation and return a single JSON object with the following fields:

{
  "is_product_name_present": boolean,
  "is_feedback_present": boolean,
  "did_user_confirm_media_availability": boolean,
  "is_media_present": boolean,
  "reply": string,
  "product_name": string,
  "feedback": string,
  "media_url": string,
  "is_feedback_session_complete": boolean
}

Field Rules:

- is_product_name_present: true if the user mentions a product name.
- is_feedback_present: true if the user gives a clear opinion, suggestion, or comment about a product.
- did_user_confirm_media_availability: true only if both is_product_name_present and is_feedback_present are true and the user explicitly states (in an inbound text) that they sent or will send media.
- is_media_present: true only if did_user_confirm_media_availability is true and at least one inbound message is of type "media".
- is_feedback_session_complete: true only if product name, feedback, and confirmed media (if applicable) are all present.
- reply: a polite and neutral string describing what the system should ask or do next based on the conversation state.

Additional Rules:
- If the product name is missing, reply must prompt for the product name.
- For the first message, avoid salutations and greetings but politely ask the user to start by providing the product name.
- If feedback is missing, reply must request the user's feedback.
- Only prompt for media if both product name and feedback are already present.
- Do not thank the user until all required information is complete.
- if any media was provided after the product name and feedback, assume that the user has confirmed the media availability and user has provided the media needed
- If the conversation is not feedback-based, reply must politely guide the user to start by providing the product name.
- Return only a valid JSON object as output. No extra text, explanations, or formatting.
        """.strip()

        logger.info(
            "LLM service initialized",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def _convert_messages_to_string(self, messages: List[Dict[str, Any]]) -> str:
        """
        Convert structured WhatsApp messages to LLM-readable dialogue format.
        """
        output = []
        for msg in messages:
            if msg["type"] == "text":
                output.append(f"{msg['direction'].capitalize()}: {msg['text']}")
            elif msg["type"] == "media":
                output.append(f"{msg['direction'].capitalize()}: [Media] {msg['url']}")
        return "\n".join(output)

    async def analyze_conversation(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a WhatsApp conversation and return extracted feedback details.

        Args:
            messages: List of WhatsApp message objects

        Returns:
            A structured JSON object with feedback analysis
        """
        try:
            user_message_content = self._convert_messages_to_string(messages)

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message_content},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            logger.info(
                "Feedback analysis generated",
                result=result,
            )

            return result

        except Exception as e:
            logger.error("Failed to analyze feedback", error=str(e))
            raise
