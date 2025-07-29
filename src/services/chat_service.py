from typing import Optional, Dict, Any
from twilio.rest import Client
from fastapi import HTTPException
import boto3
from boto3.dynamodb.conditions import Key, Attr
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Initialize DynamoDB resources
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
session_table = dynamodb.Table("sessions")
chat_table = dynamodb.Table("chats")


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

    def mark_session_as_completed(self, sender_id):
        """Mark a user's session as completed."""
        pass

    def get_user_unresolved_session_message(
        self, sender_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the active session and its unresolved inbound messages for a user.
        """
        try:
            # Get the active session
            session_response = session_table.query(
                KeyConditionExpression=Key("sender_id").eq(sender_id),
                FilterExpression=Attr("status").eq("active"),
                Limit=1,
            )
            sessions = session_response.get("Items", [])
            if not sessions:
                logger.info("No active session found", sender_id=sender_id)
                return None

            active_session = sessions[0]
            session_id = active_session["session_id"]

            # Get all inbound messages for the session
            messages = []
            last_key = None

            while True:
                query = {
                    "KeyConditionExpression": Key("sender_id").eq(sender_id),
                    "FilterExpression": (
                        Attr("chat_type").eq("inbound")
                        & Attr("session_id").eq(session_id)
                    ),
                    "ScanIndexForward": True,
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
                    "No inbound messages for session",
                    sender_id=sender_id,
                    session_id=session_id,
                )
                return None

            # Transform messages into text/media format
            transformed = []
            for msg in messages:
                content = msg.get("content", {})
                if text := content.get("text"):
                    transformed.append({"type": "text", "text": text})
                for media in content.get("media_items", []):
                    transformed.append({"type": "media", "url": media.get("url")})

            logger.info(
                "User session messages retrieved",
                message_count=len(transformed),
                sender_id=sender_id,
                session_id=session_id,
            )

            return {"messages": transformed}

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

    def reply_user(self, sender_id: str, message: str) -> Dict[str, str]:
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

        try:
            message = self.client.messages.create(
                from_=from_number, body=reply_message, to=to_number
            )

            logger.info("WhatsApp message sent", message_sid=message.sid, to=to_number)

            return {
                "to": to_number,
                "message_sid": message.sid,
                "status": message.status,
            }

        except Exception as e:
            logger.error(
                "Failed to send WhatsApp message", error=str(e), receiver_id=receiver_id
            )
            raise HTTPException(
                status_code=500, detail=f"Failed to send message: {str(e)}"
            )
