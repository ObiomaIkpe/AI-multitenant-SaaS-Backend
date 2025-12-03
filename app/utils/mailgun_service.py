import os
import httpx
from dotenv import load_dotenv

load_dotenv()

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
MAILGUN_SENDER = os.getenv("MAILGUN_SENDER")
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL", "https://api.mailgun.net/v3")


async def send_email_mailgun(to: str, subject: str, html: str):
    url = f"{MAILGUN_BASE_URL}/{MAILGUN_DOMAIN}/messages"

    auth = ("api", MAILGUN_API_KEY)
    data = {
        "from": MAILGUN_SENDER,
        "to": to,
        "subject": subject,
        "html": html,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, auth=auth, data=data)

    if response.status_code != 200:
        raise Exception(f"Mailgun Error: {response.text}")

    return response.json()
