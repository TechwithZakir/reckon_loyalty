"""Points sit in ERPNext's own Loyalty Point Entry ledger.

Sales earn and redeem through the standard Sales Invoice fields. This module adds the
two movements ERPNext has no screen for: bonus credits (welcome, birthday, campaign)
and redemptions that are not tied to an invoice (reward catalogue).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from erpnext.accounts.doctype.loyalty_point_entry.loyalty_point_entry import (
    get_loyalty_point_entries,
    get_redemption_details,
)
from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_details

# Standard redemption only consumes entries whose invoice_type matches the invoice, so
# bonus entries use the same type to stay redeemable at the till.
ENTRY_INVOICE_TYPE = "Sales Invoice"


def get_balance(customer, loyalty_program, company):
    details = get_loyalty_details(customer, loyalty_program, company=company)
    return cint(details.get("loyalty_points"))


def add_points(member, points, reason, posting_date=None):
    """Credit bonus points to a member. Returns the Loyalty Point Entry name."""
    points = cint(points)
    if points <= 0:
        return None
    member = _member(member)
    program = frappe.get_cached_doc("Loyalty Program", member.loyalty_program)
    posting_date = getdate(posting_date or today())
    entry = frappe.get_doc(
        {
            "doctype": "Loyalty Point Entry",
            "company": member.company,
            "loyalty_program": program.name,
            "loyalty_program_tier": member.tier,
            "customer": member.customer,
            "invoice_type": ENTRY_INVOICE_TYPE,
            "loyalty_points": points,
            "purchase_amount": 0,
            "expiry_date": add_days(posting_date, cint(program.expiry_duration) or 365),
            "posting_date": posting_date,
            "discretionary_reason": reason[:140],
        }
    )
    entry.flags.ignore_permissions = True
    entry.insert()
    return entry.name


def redeem_points(member, points, reason):
    """Deduct points oldest-first, the same way an invoice redemption does."""
    points = cint(points)
    if points <= 0:
        return []
    member = _member(member)
    balance = get_balance(member.customer, member.loyalty_program, member.company)
    if points > balance:
        frappe.throw(
            _("{0} has {1} points, which is not enough to redeem {2}.").format(member.member_name, balance, points)
        )

    entries = get_loyalty_point_entries(member.customer, member.loyalty_program, member.company)
    already_redeemed = get_redemption_details(member.customer, member.loyalty_program, member.company)
    remaining, created = points, []
    for entry in entries:
        available = cint(entry.loyalty_points) + cint(already_redeemed.get(entry.name))
        if available <= 0:
            continue
        take = min(available, remaining)
        doc = frappe.get_doc(
            {
                "doctype": "Loyalty Point Entry",
                "company": member.company,
                "loyalty_program": member.loyalty_program,
                "loyalty_program_tier": entry.loyalty_program_tier,
                "customer": member.customer,
                "invoice_type": ENTRY_INVOICE_TYPE,
                "redeem_against": entry.name,
                "loyalty_points": -take,
                "purchase_amount": 0,
                "expiry_date": entry.expiry_date,
                "posting_date": today(),
                "discretionary_reason": reason[:140],
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert()
        created.append(doc.name)
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0:
        frappe.throw(_("Could not allocate {0} points against unexpired entries.").format(remaining))
    return created


def get_ledger(customer, loyalty_program, limit=20):
    return frappe.get_all(
        "Loyalty Point Entry",
        filters={"customer": customer, "loyalty_program": loyalty_program},
        fields=[
            "name",
            "posting_date",
            "loyalty_points",
            "purchase_amount",
            "expiry_date",
            "invoice",
            "loyalty_program_tier",
            "discretionary_reason",
        ],
        order_by="posting_date desc, creation desc",
        limit=limit,
    )


def _member(member):
    if isinstance(member, str):
        member = frappe.get_doc("Loyalty Member", member)
    if not member.customer or not member.loyalty_program:
        frappe.throw(_("Member {0} is not linked to a customer and loyalty program.").format(member.name))
    return member
