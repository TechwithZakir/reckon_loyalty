"""Customer-facing API for the digital card and a mobile app.

These endpoints need no login. A card is addressed by its secret token (the value inside
the QR code and the card link), never by mobile number, so one member cannot read
another member's card. Both endpoints are rate limited per IP address.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from reckon_loyalty.services import members as member_service
from reckon_loyalty.services import points as points_service
from reckon_loyalty.services import rewards as reward_service
from reckon_loyalty.services.utils import get_settings, require_enabled, tier_rules


def card_data(token):
    """Everything the digital card shows. Returns None for an unknown token."""
    name = frappe.db.get_value("Loyalty Member", {"qr_token": token or ""})
    if not name:
        return None
    member = frappe.get_doc("Loyalty Member", name)
    settings = get_settings()
    profile = member_service.member_profile(member, with_qr=True)
    for private in ("customer", "member"):
        profile.pop(private, None)

    purchases = [
        {
            "date": row.posting_date,
            "store": row.loyalty_store,
            "total": row.grand_total,
            "is_return": row.is_return,
            "points_earned": cint(row.points_earned),
            "points_redeemed": cint(row.points_redeemed),
            "items": [f"{item.item_name} × {cint(item.qty)}" for item in row.get("items", [])],
        }
        for row in member_service.purchase_history(member, limit=8)
    ]
    vouchers = frappe.get_all(
        "Loyalty Reward Redemption",
        filters={"member": member.name, "status": "Issued"},
        fields=["reward", "voucher_code", "valid_till"],
        order_by="creation desc",
    )
    return {
        "brand": settings.brand_name or "Loyalty",
        "brand_color": settings.brand_color or "#111827",
        "profile": profile,
        "tiers": [
            {"tier": rule.tier_name, "min_spent": rule.min_spent, "color": rule.card_color, "benefits": rule.benefits}
            for rule in tier_rules(member.loyalty_program)
        ],
        "purchases": purchases,
        "ledger": [
            {
                "date": row.posting_date,
                "points": row.loyalty_points,
                "source": row.discretionary_reason or (_("Purchase") if row.loyalty_points > 0 else _("Redeemed")),
                "expires": row.expiry_date,
            }
            for row in points_service.get_ledger(member.customer, member.loyalty_program, limit=8)
        ],
        "rewards": reward_service.available_rewards(member),
        "vouchers": vouchers,
    }


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_card(token):
    """JSON form of the digital card, for a mobile app."""
    data = card_data(token)
    if not data:
        frappe.throw(_("Card not found."), frappe.DoesNotExistError)
    return data


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def join(member_name, mobile_no, email=None, gender=None, date_of_birth=None, city=None, store=None, channel="Web", consent=0):
    """Self-registration from the website or the app."""
    require_enabled()
    if not cint(consent):
        frappe.throw(_("Please accept the membership terms to continue."))
    if len((member_name or "").strip()) < 3:
        frappe.throw(_("Please enter your full name."))

    existing = member_service.get_member(mobile_no, throw=False)
    if existing:
        # Never hand out an existing card to whoever typed the number: resend the link to the phone.
        from reckon_loyalty.services.campaigns import send_welcome

        send_welcome(existing)
        return {"status": "exists", "message": _("This mobile number is already a member. We have sent the card link by SMS.")}

    member = member_service.enroll(
        member_name,
        mobile_no,
        channel="Mobile App" if channel == "Mobile App" else "Web",
        email=email,
        gender=gender if gender in ("Male", "Female", "Other") else None,
        date_of_birth=date_of_birth,
        city=city,
        home_store=store if store and frappe.db.exists("Loyalty Store", store) else None,
    )
    return {"status": "created", "card_number": member.card_number, "card_url": f"/card/{member.qr_token}"}
