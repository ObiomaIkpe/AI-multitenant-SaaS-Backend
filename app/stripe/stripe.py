import stripe
from fastapi import APIRouter, Request, HTTPException
from config import settings

router = APIRouter()

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle event types
    if event['type'] == 'invoice.paid':
        # update organization subscription status
        pass

    return {"status": "success"}
