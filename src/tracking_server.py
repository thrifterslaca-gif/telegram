from aiohttp import web
import logging
from src.analytics import track_conversion
from src.config import TRACKING_SERVER_PORT

logger = logging.getLogger(__name__)

async def handle_tracking(request):
    """
    Handles the tracking redirection.
    URL: /tracking?mid={message_index}
    """
    try:
        # Extract params
        mid = request.query.get('mid')
        # We need chat_id for GA. In the spec, it says "Client ID... derived from the user's Telegram chat_id".
        # However, the current message generation (src/messages.py) puts a static URL in the button.
        # To strictly follow the spec: "The URL link embedded in the CTA must be dynamically generated... derived from the user's Telegram chat_id".
        # This means we can't fully pre-generate the static JSON content in the DB if the URL needs to be unique PER USER.
        # OR we generate the URL at send-time.

        # But wait, src/messages.py generates the content template.
        # The logic in send_paced_message_callback needs to INJECT the chat_id into the URL if it's not already there.
        # Or we rely on a cookie? No, Telegram webview/browser.

        # Let's assume the URL logic in src/messages.py is a TEMPLATE and we replace it at send time?
        # Or better, we pass `cid` (chat_id) in the query string if we can.

        # Checking implementation in send_paced_message_callback:
        # It parses JSON. It does not currently inject chat_id.

        # To make this work, I need to update send_paced_message_callback to append `&cid={chat_id}` to the URL in the buttons.

        cid = request.query.get('cid')

        if mid and cid:
            # Fire GA Event
            await track_conversion(int(cid), int(mid))

        # Redirect
        # For this example, we redirect to a dummy offer page
        return web.HTTPFound('http://example.com/offer')

    except Exception as e:
        logger.error(f"Tracking error: {e}")
        return web.Response(text="Error processing request", status=500)

def start_tracking_server():
    """
    Starts the aiohttp server.
    """
    app = web.Application()
    app.add_routes([web.get('/tracking', handle_tracking)])
    runner = web.AppRunner(app)
    return runner
