import frappe

from reckon_loyalty.services.utils import get_settings, tier_rules

no_cache = 1


def get_context(context):
    settings = get_settings()
    context.no_cache = 1
    context.brand = settings.brand_name or "Loyalty"
    context.brand_color = settings.brand_color or "#111827"
    context.welcome_bonus = settings.welcome_bonus_points
    context.tiers = tier_rules(settings.loyalty_program)
    context.stores = frappe.get_all(
        "Loyalty Store", filters={"is_active": 1}, fields=["name", "city"], order_by="name"
    )
    context.csrf_token = frappe.sessions.get_csrf_token()
    return context
