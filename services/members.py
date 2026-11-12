import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, today

from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
    get_loyalty_program_details_with_points,
)

from reckon_loyalty.services import points as points_service
from reckon_loyalty.services.utils import (
    QR_PREFIX,
    card_url,
    get_settings,
    normalize_mobile,
    qr_payload,
    qr_svg,
    tier_rules,
)


# ---------------------------------------------------------------- identification
def resolve_member(identifier):
    """Find a member from whatever the till scanned or typed.

    Accepts the QR payload, the digital card link, the card number or the mobile number.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    token = None
    if identifier.startswith(QR_PREFIX):
        token = identifier[len(QR_PREFIX) :]
    else:
        match = re.search(r"/card/([A-Za-z0-9]+)", identifier) or re.search(r"[?&]token=([A-Za-z0-9]+)", identifier)
        if match:
            token = match.group(1)
    if token:
        return frappe.db.get_value("Loyalty Member", {"qr_token": token})

    member = frappe.db.get_value("Loyalty Member", {"card_number": identifier.upper()})
    if member:
        return member
    if frappe.db.exists("Loyalty Member", identifier):
        return identifier
    mobile = normalize_mobile(identifier, strict=False)
    if mobile:
        return frappe.db.get_value("Loyalty Member", {"mobile_no": mobile})
    return None


def get_member(identifier, throw=True):
    name = resolve_member(identifier)
    if not name:
        if throw:
            frappe.throw(_("No loyalty member found for {0}.").format(identifier), frappe.DoesNotExistError)
        return None
    return frappe.get_doc("Loyalty Member", name)


def enroll(member_name, mobile_no, channel="Back Office", **details):
    """Create a member (and the ERPNext Customer behind it)."""
    allowed = ("email", "gender", "date_of_birth", "city", "home_store", "sms_opt_in", "email_opt_in", "enrollment_date")
    doc = frappe.get_doc(
        {
            "doctype": "Loyalty Member",
            "member_name": (member_name or "").strip(),
            "mobile_no": mobile_no,
            "enrollment_channel": channel,
            **{key: details[key] for key in allowed if details.get(key) not in (None, "")},
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc


# ---------------------------------------------------------------- profile
def member_profile(member, with_qr=False):
    """The member as the POS, the mobile app and the digital card see it."""
    if isinstance(member, str):
        member = frappe.get_doc("Loyalty Member", member)
    program = frappe.get_cached_doc("Loyalty Program", member.loyalty_program) if member.loyalty_program else None
    rules = tier_rules(member.loyalty_program)
    balance = (
        points_service.get_balance(member.customer, member.loyalty_program, member.company) if program else 0
    )

    current, upcoming = None, None
    for index, rule in enumerate(rules):
        if rule.tier_name == member.tier:
            current = rule
            upcoming = rules[index + 1] if index + 1 < len(rules) else None
    if not current and rules:
        current, upcoming = rules[0], (rules[1] if len(rules) > 1 else None)

    spend = flt(member.lifetime_spend)
    progress = 100
    if upcoming:
        span = flt(upcoming.min_spent) - flt(current.min_spent)
        progress = max(0, min(100, round((spend - flt(current.min_spent)) / span * 100))) if span else 100

    conversion = flt(program.conversion_factor) if program else 0
    profile = {
        "member": member.name,
        "member_name": member.member_name,
        "first_name": member.member_name.split(" ")[0],
        "card_number": member.card_number,
        "mobile_no": member.mobile_no,
        "email": member.email,
        "status": member.status,
        "customer": member.customer,
        "home_store": member.home_store,
        "member_since": member.enrollment_date,
        "tier": current.tier_name if current else member.tier,
        "tier_color": current.card_color if current else "#1f2937",
        "tier_benefits": current.benefits if current else "",
        "earn_rule": _earn_rule(current),
        "next_tier": upcoming.tier_name if upcoming else None,
        "spend_to_next_tier": max(0, flt(upcoming.min_spent) - spend) if upcoming else 0,
        "tier_progress": progress,
        "points_balance": balance,
        "points_value": flt(balance * conversion, 2),
        "point_value": conversion,
        "points_expiring_30d": cint(member.points_expiring_30d),
        "lifetime_points": cint(member.lifetime_points),
        "lifetime_spend": spend,
        "total_orders": cint(member.total_orders),
        "last_purchase_date": member.last_purchase_date,
        "qr_payload": qr_payload(member.qr_token),
        "card_url": card_url(member.qr_token),
    }
    if with_qr:
        profile["qr_svg"] = qr_svg(profile["qr_payload"])
    return profile


def _earn_rule(rule):
    if not rule or not flt(rule.collection_factor):
        return ""
    return _("1 point for every {0} spent").format(frappe.format_value(rule.collection_factor, {"fieldtype": "Int"}))


def purchase_history(member, limit=20):
    if isinstance(member, str):
        member = frappe.get_doc("Loyalty Member", member)
    store_field = ", si.loyalty_store" if frappe.get_meta("Sales Invoice").has_field("loyalty_store") else ", null as loyalty_store"
    invoices = frappe.db.sql(
        f"""
        select si.name, si.posting_date, si.grand_total, si.is_return, si.loyalty_points as points_redeemed,
            si.loyalty_amount, si.total_qty {store_field},
            (select coalesce(sum(e.loyalty_points), 0) from `tabLoyalty Point Entry` e
                where e.invoice = si.name and e.loyalty_points > 0) as points_earned
        from `tabSales Invoice` si
        where si.docstatus = 1 and si.customer = %s and si.company = %s
        order by si.posting_date desc, si.creation desc
        limit %s
        """,
        (member.customer, member.company, cint(limit)),
        as_dict=True,
    )
    if invoices:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": ["in", [row.name for row in invoices]]},
            fields=["parent", "item_code", "item_name", "qty", "rate", "amount"],
            order_by="idx asc",
        )
        by_invoice = {}
        for item in items:
            by_invoice.setdefault(item.parent, []).append(item)
        for row in invoices:
            row["items"] = by_invoice.get(row.name, [])
    return invoices


# ---------------------------------------------------------------- invoice hooks
def stamp_invoice(doc, method=None):
    """Tag invoices of loyalty members so they earn points and show up in member history."""
    if not doc.get("customer") or not doc.meta.has_field("loyalty_member"):
        return
    member = frappe.db.get_value(
        "Loyalty Member", {"customer": doc.customer}, ["name", "loyalty_program", "company", "status"], as_dict=True
    )
    if not member or member.company != doc.company:
        return
    doc.loyalty_member = member.name
    if member.status == "Active" and member.loyalty_program and not doc.get("loyalty_program"):
        doc.loyalty_program = member.loyalty_program


def on_invoice_change(doc, method=None):
    member = doc.get("loyalty_member") or frappe.db.get_value("Loyalty Member", {"customer": doc.customer})
    if member:
        refresh_member_stats(member)


# ---------------------------------------------------------------- cached statistics
def refresh_member_stats(member_name):
    member = frappe.db.get_value(
        "Loyalty Member", member_name, ["name", "customer", "company", "loyalty_program"], as_dict=True
    )
    if not member or not member.customer:
        return

    sales = frappe.db.sql(
        """
        select count(case when is_return = 0 then 1 end) as orders,
            coalesce(sum(base_grand_total), 0) as spend,
            min(case when is_return = 0 then posting_date end) as first_date,
            max(case when is_return = 0 then posting_date end) as last_date
        from `tabSales Invoice`
        where docstatus = 1 and customer = %s and company = %s
        """,
        (member.customer, member.company),
        as_dict=True,
    )[0]

    values = {
        "total_orders": cint(sales.orders),
        "lifetime_spend": flt(sales.spend),
        "avg_basket": flt(sales.spend) / sales.orders if sales.orders else 0,
        "first_purchase_date": sales.first_date,
        "last_purchase_date": sales.last_date,
        "days_since_last_purchase": date_diff(today(), sales.last_date) if sales.last_date else 0,
    }
    values["rfm_segment"] = classify(values["total_orders"], values["days_since_last_purchase"], sales.last_date)

    if member.loyalty_program:
        ledger = frappe.db.sql(
            """
            select coalesce(sum(case when loyalty_points > 0 then loyalty_points end), 0) as earned,
                coalesce(-sum(case when loyalty_points < 0 then loyalty_points end), 0) as redeemed
            from `tabLoyalty Point Entry`
            where customer = %s and loyalty_program = %s and company = %s
            """,
            (member.customer, member.loyalty_program, member.company),
            as_dict=True,
        )[0]
        expiring = frappe.db.sql(
            """
            select coalesce(sum(e.loyalty_points + coalesce((
                select sum(r.loyalty_points) from `tabLoyalty Point Entry` r where r.redeem_against = e.name
            ), 0)), 0)
            from `tabLoyalty Point Entry` e
            where e.customer = %s and e.loyalty_program = %s and e.company = %s
                and e.loyalty_points > 0 and e.expiry_date between %s and %s
            """,
            (member.customer, member.loyalty_program, member.company, today(), add_days(today(), 30)),
        )[0][0]
        details = get_loyalty_program_details_with_points(
            member.customer,
            loyalty_program=member.loyalty_program,
            company=member.company,
            include_expired_entry=True,
            silent=True,
        )
        values.update(
            {
                "points_balance": points_service.get_balance(member.customer, member.loyalty_program, member.company),
                "lifetime_points": cint(ledger.earned),
                "points_redeemed": cint(ledger.redeemed),
                "points_expiring_30d": max(0, cint(expiring)),
                "tier": details.get("tier_name"),
            }
        )
        if details.get("tier_name"):
            frappe.db.set_value(
                "Customer", member.customer, "loyalty_program_tier", details.get("tier_name"), update_modified=False
            )

    frappe.db.set_value("Loyalty Member", member.name, values, update_modified=False)
    return values


def classify(orders, days_since, last_date):
    if not orders or not last_date:
        return "No Purchase"
    if days_since <= 30 and orders >= 6:
        return "Champion"
    if days_since <= 60 and orders >= 3:
        return "Loyal"
    if orders == 1 and days_since <= 45:
        return "New"
    if days_since <= 60:
        return "Promising"
    if days_since <= 120:
        return "At Risk"
    return "Lapsed"


def refresh_all_members():
    for name in frappe.get_all("Loyalty Member", pluck="name"):
        refresh_member_stats(name)
    frappe.db.commit()


def award_birthday_bonus():
    settings = get_settings()
    bonus = cint(settings.birthday_bonus_points)
    if not settings.enabled or not bonus:
        return
    current = getdate(today())
    members = frappe.db.sql(
        """
        select name from `tabLoyalty Member`
        where status = 'Active' and date_of_birth is not null
            and month(date_of_birth) = %s and day(date_of_birth) = %s
        """,
        (current.month, current.day),
        pluck=True,
    )
    reason = f"Birthday bonus {current.year}"
    for name in members:
        member = frappe.get_doc("Loyalty Member", name)
        if not member.loyalty_program or frappe.db.exists(
            "Loyalty Point Entry", {"customer": member.customer, "discretionary_reason": reason}
        ):
            continue
        points_service.add_points(member, bonus, reason)
        refresh_member_stats(name)
    frappe.db.commit()


# ---------------------------------------------------------------- desk helpers
@frappe.whitelist()
def get_member_card(member):
    """Card, QR code and history for the Loyalty Member form."""
    doc = frappe.get_doc("Loyalty Member", member)
    doc.check_permission("read")
    profile = member_profile(doc, with_qr=True)
    return {
        "profile": profile,
        "history": purchase_history(doc, limit=15),
        "ledger": points_service.get_ledger(doc.customer, doc.loyalty_program, limit=15) if doc.loyalty_program else [],
    }


@frappe.whitelist()
def refresh_member(member):
    doc = frappe.get_doc("Loyalty Member", member)
    doc.check_permission("write")
    return refresh_member_stats(member)


@frappe.whitelist()
def adjust_points(member, points, reason):
    """Manual credit (positive) or debit (negative) by a loyalty manager."""
    frappe.only_for(("Loyalty Manager", "System Manager"))
    points = cint(points)
    if not points or not (reason or "").strip():
        frappe.throw(_("Enter the points and a reason."))
    doc = frappe.get_doc("Loyalty Member", member)
    label = f"Manual adjustment: {reason.strip()}"
    if points > 0:
        points_service.add_points(doc, points, label)
    else:
        points_service.redeem_points(doc, -points, label)
    return refresh_member_stats(member)
