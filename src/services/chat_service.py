from twilio.rest import Client
from fastapi import HTTPException
from src.utils.logger import get_logger

logger = get_logger(__name__)

class ChatService:
    def __init__(self, config):
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
        pass

    def get_reply_message(self, sender_id, message):
        return message

    def reply_user(self, sender_id, message):
        receiver_id = f"+{sender_id}"
        reply_message = self.get_reply_message(sender_id, message)

        client = self.client

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
            message = client.messages.create(
                from_=from_number, body=reply_message, to=to_number
            )

            logger.info(f"WhatsApp message sent: {message.sid} to {to_number}")

            return {
                "to": to_number,
                "message_sid": message.sid,
                "status": message.status,
            }

        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {receiver_id}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to send message: {str(e)}"
            )
