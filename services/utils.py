import io
import re

import frappe
from frappe import _
from frappe.utils import get_url

QR_PREFIX = "RL1:"
MANAGER_ROLES = ("Loyalty Manager", "System Manager")
STAFF_ROLES = ("Loyalty Manager", "Loyalty User", "Loyalty POS", "System Manager")


def get_settings():
    return frappe.get_cached_doc("Loyalty Settings")


def require_enabled():
    settings = get_settings()
    if not settings.enabled:
        frappe.throw(_("Loyalty is switched off in Loyalty Settings."))
    if not settings.company or not settings.loyalty_program:
        frappe.throw(_("Set the Company and Loyalty Program in Loyalty Settings first."))
    return settings


def require_role(roles=STAFF_ROLES):
    if frappe.session.user == "Administrator":
        return
    if not set(roles) & set(frappe.get_roles()):
        frappe.throw(_("You are not allowed to use the loyalty service."), frappe.PermissionError)


def normalize_mobile(value, strict=True):
    """Bangladesh mobile numbers are stored as 11 digits starting with 01."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("880") and len(digits) == 13:
        digits = digits[2:]
    elif digits.startswith("1") and len(digits) == 10:
        digits = "0" + digits
    if strict and not re.fullmatch(r"01[3-9]\d{8}", digits):
        frappe.throw(_("{0} is not a valid mobile number. Use the format 01XXXXXXXXX.").format(value or ""))
    return digits


def card_url(token):
    return get_url(f"/card/{token}")


def qr_payload(token):
    return f"{QR_PREFIX}{token}"


def qr_svg(data, scale=5):
    """Inline SVG QR code. pyqrcode ships with Frappe (two-factor auth uses it)."""
    try:
        import pyqrcode
    except ImportError:
        return ""
    buffer = io.BytesIO()
    pyqrcode.create(data, error="M").svg(
        buffer, scale=scale, quiet_zone=2, xmldecl=False, svgclass="rl-qr", module_color="#111111", background="#ffffff"
    )
    return buffer.getvalue().decode("utf-8")


def tier_rules(loyalty_program):
    """Tiers of the ERPNext Loyalty Program, lowest first."""
    if not loyalty_program:
        return []
    rows = frappe.get_all(
        "Loyalty Program Collection",
        filters={"parent": loyalty_program, "parenttype": "Loyalty Program"},
        fields=["tier_name", "min_spent", "collection_factor"],
        order_by="min_spent asc",
    )
    presentation = {row.tier_name: row for row in get_settings().tiers}
    for row in rows:
        extra = presentation.get(row.tier_name)
        row.card_color = (extra.card_color if extra else None) or "#1f2937"
        row.benefits = (extra.benefits if extra else None) or ""
    return rows


def tier_rank(loyalty_program, tier_name):
    for index, row in enumerate(tier_rules(loyalty_program)):
        if row.tier_name == tier_name:
            return index
    return -1
