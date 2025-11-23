import json
from src.config import TRACKING_BASE_URL

# Configuration for the 100-step sequence
# This helps populate the SequenceTemplate table

def generate_default_sequence(template_id="SEQ_100_STEP_ALPHA"):
    """
    Generates the list of 100 messages with their phases and delays.

    Phases:
    P1: M1-M10 (30 mins)
    P2: M11-M60 (4 hours = 240 mins)
    P3: M61-M90 (6 hours = 360 mins)
    P4: M91-M100 (24 hours = 1440 mins)
    """
    messages = []

    # Phase 1: Initiation & Qualification
    for i in range(1, 11):
        messages.append({
            "template_id": template_id,
            "message_index": i,
            "phase": "P1",
            "content_payload": json.dumps({"text": f"Phase 1 Message {i}: Welcome and Qualification."}),
            "base_delay_minutes": 30
        })

    # Phase 2: Nurturing & Trust Building
    for i in range(11, 61):
        messages.append({
            "template_id": template_id,
            "message_index": i,
            "phase": "P2",
            "content_payload": json.dumps({"text": f"Phase 2 Message {i}: Nurturing content."}),
            "base_delay_minutes": 240
        })

    # Phase 3: Conversion & Offer Delivery
    for i in range(61, 91):
        # Use the tracking server URL
        cta_url = f"{TRACKING_BASE_URL}/tracking?mid={i}"
        payload = {
            "text": f"Phase 3 Message {i}: Exclusive Offer.",
            "buttons": [[{"text": "View Offer", "url": cta_url}]]
        }
        messages.append({
            "template_id": template_id,
            "message_index": i,
            "phase": "P3",
            "content_payload": json.dumps(payload),
            "base_delay_minutes": 360
        })

    # Phase 4: Drop-Off Re-engagement
    for i in range(91, 101):
        messages.append({
            "template_id": template_id,
            "message_index": i,
            "phase": "P4",
            "content_payload": json.dumps({"text": f"Phase 4 Message {i}: Last chance re-engagement."}),
            "base_delay_minutes": 1440
        })

    return messages
