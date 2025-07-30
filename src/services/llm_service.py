import json
from typing import List, Dict, Any
from openai import AsyncOpenAI
from src.utils.logger import get_logger
import datetime

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

You will receive a chronological list of messages exchanged between a user and the system. Each message includes:
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
  "is_feedback_session_complete": boolean,
  "is_x_rated_conversation": boolean,
  "is_crime_rated_conversation": boolean,
  "is_immoral_conversation": boolean,
  "is_too_short": boolean,
  "is_irrelevant": boolean
}

### Field Definitions:

- is_product_name_present: true if the user mentions a product name.
- is_feedback_present: true if the user gives a clear opinion, suggestion, or comment about a product.
- did_user_confirm_media_availability: true only if both is_product_name_present and is_feedback_present are true and the user explicitly states (in an inbound text) that they sent or will send media.
- is_media_present: true only if did_user_confirm_media_availability is true and at least one inbound message is of type "media".
- is_feedback_session_complete: true only if product name, feedback, and confirmed media (if applicable) are all present.
- reply: a brief, polite, and neutral instruction that guides the user on what to do next based on the state.
- product_name: exact product name if mentioned, else empty string.
- feedback: user feedback if present, else empty string.
- media_urls: if a valid inbound media message exists, include the media URL, else empty string.
- is_x_rated_conversation: true if the conversation includes explicit, offensive, or sexual language from the user.
- is_crime_rated_conversation: true if the conversation includes illegal activity references (e.g. theft, fraud, threats).
- is_immoral_conversation: true if the user uses language or ideas that are morally questionable (e.g. hate speech, unethical behavior).
- is_too_short: true if the user's latest inbound text message contains fewer than 100 characters (excluding whitespace).
- is_irrelevant: true if the user's message is clearly unrelated to product feedback or support (e.g., “I am Jesus”).

### Additional Instructions:

- If the product name is missing, reply must prompt for it.
- If this is the first inbound message and it includes a greeting or salutation, begin your reply with a casual greeting.
- If feedback is missing, reply must ask for feedback.
- Only prompt for media if both product name and feedback are already present.
- Do not thank the user until all required information is complete.
- If media is provided after product name and feedback, assume media was confirmed and delivered.
- If the conversation is not about feedback, politely ask the user to begin with the product name.
- If any message includes explicit, illegal, immoral, irrelevant, or inappropriate content, the reply must politely redirect the user to only send messages relevant to product feedback.
- If the message is too short and does not convey useful information, reply must ask the user to be more specific.
- Return a strictly valid JSON object only. Do not include any explanations or formatting.
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

    async def analyze_conversation(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze a WhatsApp conversation and return extracted feedback details.

        Args:
            messages: List of WhatsApp message objects

        Returns:
            A structured JSON object with feedback analysis
        """
        try:
            # Check if any message exceeds 1000 characters
            for msg in messages:
                if msg["type"] == "text" and msg.get("text"):
                    if len(msg["text"]) > 1000:
                        logger.warning(
                            "Message exceeds character limit",
                            message_length=len(msg["text"]),
                            direction=msg.get("direction", "unknown"),
                        )
                        return {
                            "is_product_name_present": False,
                            "is_feedback_present": False,
                            "did_user_confirm_media_availability": False,
                            "is_media_present": False,
                            "reply": "Message too long. Please shorten it to under 1000 characters and try again.",
                            "product_name": "",
                            "feedback": "",
                            "media_url": "",
                            "is_feedback_session_complete": False,
                            "is_x_rated_conversation": False,
                            "is_crime_rated_conversation": False,
                            "is_immoral_conversation": False,
                            "is_too_short": False,
                            "is_irrelevant": False,
                            "should_persist_reply": True,
                        }

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

            if (
                result.get("is_x_rated_conversation", False)
                or result.get("is_crime_rated_conversation", False)
                or result.get("is_immoral_conversation", False)
                or result.get("is_irrelevant", False)
            ):
                result["should_persist_reply"] = False
                result["reply"] = (
                    "We detected misuse of the system, and your access has been temporarily suspended for 10 minutes. Thank you for your understanding."
                )
                result["user_limited_until"] = (
                    datetime.datetime.now() + datetime.timedelta(minutes=2)
                ).isoformat()
                result["reopen_session"] = True

                return result

            if result.get("is_too_short", False):
                result["should_persist_reply"] = False
                result["reply"] = "Your message is too short."
                return result

            return result

        except Exception as e:
            logger.error("Failed to analyze feedback", error=str(e))
            return {
                "is_product_name_present": False,
                "is_feedback_present": False,
                "did_user_confirm_media_availability": False,
                "is_media_present": False,
                "reply": "Failed to process your message. Please try again.",
                "product_name": "",
                "feedback": "",
                "media_url": "",
                "is_feedback_session_complete": False,
                "is_x_rated_conversation": False,
                "is_crime_rated_conversation": False,
                "is_immoral_conversation": False,
                "is_too_short": False,
                "is_irrelevant": False,
                "should_persist_reply": False,
            }
