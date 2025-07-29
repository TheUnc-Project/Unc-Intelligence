from typing import Optional, Dict, Any
from twilio.rest import Client
from fastapi import HTTPException
import boto3
from boto3.dynamodb.conditions import Key, Attr
from src.utils.logger import get_logger
import uuid
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = get_logger(__name__)

# Initialize DynamoDB resources
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
session_table = dynamodb.Table("sessions")
chat_table = dynamodb.Table("chats")

# Thread pool for async operations
thread_pool = ThreadPoolExecutor(max_workers=10)


class ChatService:
    def __init__(self, config):
        """Initialize ChatService with Twilio configuration."""
        if not config:
            raise ValueError("Configuration is required")

        self.account_sid = config.get("TWILIO_ACCOUNT_SID")
        self.auth_token = config.get("TWILIO_AUTH_TOKEN")
        self.from_number = config.get("TWILIO_WHATSAPP_FROM")

        # Validate required configurations
        if not all([self.account_sid, self.auth_token, self.from_number]):
            logger.warning("Missing required Twilio configurations")
            logger.debug(f"TWILIO_ACCOUNT_SID present: {bool(self.account_sid)}")
            logger.debug(f"TWILIO_AUTH_TOKEN present: {bool(self.auth_token)}")
            logger.debug(f"TWILIO_WHATSAPP_FROM present: {bool(self.from_number)}")
            raise ValueError(
                "Missing required Twilio configurations. Please set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM"
            )

        self.client = Client(self.account_sid, self.auth_token)

    async def send_whatsapp_message(
        self, from_number: str, to_number: str, reply_message: str
    ) -> Dict[str, str]:
        """Send WhatsApp message using Twilio in a separate thread."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            thread_pool,
            lambda: self.client.messages.create(
                from_=from_number, body=reply_message, to=to_number
            ),
        )

    async def save_chat_message(self, message_data: Dict[str, Any]):
        """Save chat message to DynamoDB in a separate thread."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            thread_pool, lambda: chat_table.put_item(Item=message_data)
        )

    def mark_session_as_completed(self, sender_id):
        """Mark a user's session as completed."""
        pass

    def get_user_unresolved_session_message(
        self, sender_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the active session and all its messages (both inbound and outbound).
        """
        try:
            # Get the active session using SenderSessionsIndex
            session_response = session_table.query(
                IndexName="SenderSessionsIndex",
                KeyConditionExpression=Key("sender_id").eq(sender_id),
                FilterExpression=Attr("status").eq("active"),
                ScanIndexForward=False,  # Get most recent first
                Limit=1,
            )
            sessions = session_response.get("Items", [])
            if not sessions:
                logger.info("No active session found", sender_id=sender_id)
                return None

            active_session = sessions[0]
            session_id = active_session["session_id"]

            # Get all messages for the session using SessionIndex
            messages = []
            last_key = None

            while True:
                query = {
                    "IndexName": "SessionIndex",
                    "KeyConditionExpression": Key("session_id").eq(session_id),
                    "ScanIndexForward": True,  # Get messages in chronological order
                }
                if last_key:
                    query["ExclusiveStartKey"] = last_key

                response = chat_table.query(**query)
                messages.extend(response.get("Items", []))
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break

            if not messages:
                logger.info(
                    "No messages for session",
                    sender_id=sender_id,
                    session_id=session_id,
                )
                return None

            # Transform messages into text/media format
            transformed = []
            for msg in messages:
                content = msg.get("content", {})
                direction = (
                    "inbound" if msg.get("chat_type") == "inbound" else "outbound"
                )

                if text := content.get("text"):
                    transformed.append(
                        {"type": "text", "text": text, "direction": direction}
                    )
                for media in content.get("media_items", []):
                    transformed.append(
                        {
                            "type": "media",
                            "url": media.get("url"),
                            "direction": direction,
                        }
                    )

            logger.info(
                "User session messages retrieved",
                message_count=len(transformed),
                sender_id=sender_id,
                session_id=session_id,
            )

            return {"messages": transformed, "session_id": session_id}

        except Exception as e:
            logger.error(
                "Failed to get unresolved session messages",
                error=str(e),
                sender_id=sender_id,
            )
            raise

    def get_reply_message(self, sender_id: str, message: str) -> str:
        """Get the reply message for a user's message."""
        return message

    async def reply_user(self, sender_id: str, message: str) -> Dict[str, str]:
        """
        Send a WhatsApp reply to a user.

        Args:
            sender_id: The user's WhatsApp ID
            message: The message to send

        Returns:
            Dict containing message details (to, message_sid, status)

        Raises:
            HTTPException: If message sending fails
        """
        try:
            receiver_id = f"+{sender_id}"

            user_unresolved_session_message = self.get_user_unresolved_session_message(
                sender_id
            )

            logger.info(
                "User unresolved session message",
                user_unresolved_session_message=user_unresolved_session_message,
            )

            reply_message = self.get_reply_message(sender_id, message)

            # Format WhatsApp numbers
            from_number = (
                self.from_number
                if self.from_number.startswith("whatsapp:")
                else f"whatsapp:{self.from_number}"
            )
            to_number = (
                receiver_id
                if receiver_id.startswith("whatsapp:")
                else f"whatsapp:{receiver_id}"
            )

            # Generate message_id
            message_id = str(uuid.uuid4())
            timestamp = int(time.time())

            # Prepare chat message data
            chat_data = {
                "sender_id": sender_id,
                "message_id": message_id,
                "chat_type": "outbound",
                "session_id": user_unresolved_session_message["session_id"],
                "created_at": timestamp,
                "content": {"text": reply_message, "media_count": 0, "segments": 1},
                "metadata": {"message_id": message_id, "status": "sent"},
            }

            # Run Twilio call and DynamoDB save in parallel
            whatsapp_task = self.send_whatsapp_message(
                from_number, to_number, reply_message
            )
            save_task = self.save_chat_message(chat_data)

            # Wait for both operations to complete
            whatsapp_result, _ = await asyncio.gather(
                whatsapp_task, save_task, return_exceptions=True
            )

            logger.info(
                "WhatsApp message sent and saved",
                message_id=message_id,
                twilio_sid=whatsapp_result.sid,
                to=to_number,
            )

        except Exception as e:
            logger.error(
                "Failed to send WhatsApp message", error=str(e), receiver_id=receiver_id
            )
