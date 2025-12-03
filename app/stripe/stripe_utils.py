import stripe
from app.config import StripeConfig

def create_organization_in_stripe(org_name: str, billing_email: str):
    customer = stripe.Customer.create(
        name=org_name,
        email=billing_email,
    )
    return customer['id']

def create_subscription(org, tier: str):
    price_id = StripeConfig.STRIPE_PRICE_IDS[tier]
    if price_id is None:
        # Free tier, no subscription needed
        return None

    subscription = stripe.Subscription.create(
        customer=org.stripe_customer_id,
        items=[{'price': price_id}],
        expand=['latest_invoice.payment_intent'],
    )

    org.stripe_subscription_id = subscription['id']
    org.subscription_tier = tier
    org.subscription_status = subscription['status']
