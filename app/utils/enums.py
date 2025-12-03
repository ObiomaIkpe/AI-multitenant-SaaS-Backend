from enum import Enum

class SubscriptionStatus(Enum):
    trial = "trial"
    active = "active"
    canceled = "canceled"
    past_due = "past_due"

class SubscriptionTier(Enum):
    free = "free"
    pro = "shared"
    enterprise = "enterprise"


class UserStatus(Enum):
    active = "active"
    inactive = "inactive"
    pending_activation = "pending_activation"
    suspended = "suspended"
    deleted = "deleted"


class MessageRole(Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


