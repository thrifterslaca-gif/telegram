import httpx
import logging
from src.config import GA_MEASUREMENT_ID, GA_API_SECRET

logger = logging.getLogger(__name__)

async def send_ga_event(chat_id: int, event_name: str, params: dict = None):
    """
    Sends an event to Google Analytics via Measurement Protocol.

    Args:
        chat_id: The Telegram User ID (used as client_id).
        event_name: The name of the event (e.g., 'M1_SENT', 'M65_CTA_Click').
        params: Additional event parameters.
    """
    if not params:
        params = {}

    url = f"https://www.google-analytics.com/mp/collect?measurement_id={GA_MEASUREMENT_ID}&api_secret={GA_API_SECRET}"

    payload = {
        "client_id": str(chat_id),
        "events": [{
            "name": event_name,
            "params": params
        }]
    }

    # Add session_id if not present to ensure tracking continuity (optional)
    if "session_id" not in params:
        # For simplicity, we are not managing session_ids strictly here,
        # but in a real app, you might want to generate or persist one.
        pass

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.debug(f"GA Event Sent: {event_name} for User {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send GA event: {e}")

async def track_message_sent(chat_id: int, message_index: int, phase: str):
    """
    Wrapper to track a message sent event.
    """
    event_name = f"M{message_index}_SENT"
    params = {
        "event_category": "Niche_Model_Funnel_V1",
        "event_action": event_name,
        "message_index": message_index,
        "phase": phase
    }
    await send_ga_event(chat_id, event_name, params)

async def track_conversion(chat_id: int, message_index: int):
    """
    Wrapper to track a conversion/CTA click event.
    """
    event_name = f"M{message_index}_CTA_Click"
    params = {
        "event_category": "Niche_Model_Funnel_V1",
        "event_action": event_name,
        "message_index": message_index
    }
    await send_ga_event(chat_id, event_name, params)
