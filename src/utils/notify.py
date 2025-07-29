import httpx
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def notify_reply_service(sender_id: str, message: str = "") -> None:
    """
    Notify the reply service to process messages for a sender.

    Args:
        sender_id: The sender ID to process
        message: Optional message content (can be empty string)
    """
    url = "https://intelligence.theuncproject.com/reply/"
    payload = {
        "sender_id": sender_id,
        "message": message,  # Can be empty string if not needed
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            logger.info(
                "Successfully notified reply service",
                sender_id=sender_id,
                status_code=response.status_code,
            )

    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error notifying reply service",
            sender_id=sender_id,
            status_code=e.response.status_code,
            detail=e.response.text,
        )
        raise
    except Exception as e:
        logger.error("Error notifying reply service", sender_id=sender_id, error=str(e))
        raise
