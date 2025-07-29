from fastapi import APIRouter, HTTPException
import logging
from pydantic import BaseModel

router = APIRouter()
router.config = {}
router.services = {}

logging.basicConfig(level=logging.INFO)

# Define a model for the request body
class ReplyRequest(BaseModel):
    sender_id: str
    message: str

@router.post("/")
async def reply_user(request: ReplyRequest):
    try:
        logging.info(f"Received request to reply to user {request.sender_id}")
        chat_service = router.services["chat_service"]
        chat_service.reply_user(request.sender_id, request.message)

        return {"message": "Reply sent successfully."}
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
