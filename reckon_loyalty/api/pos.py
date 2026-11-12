"""POS integration API.

Every method is a normal Frappe endpoint:

    POST /api/method/reckon_loyalty.api.pos.<method>
    Authorization: token <api_key>:<api_secret>

The calling user needs the "Loyalty POS" role (or Loyalty User / Loyalty Manager).
Sales are posted as ERPNext Sales Invoices in real time, so points, tier, stock and
accounts are all updated by the time the response returns.
"""

import json
import time

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowtime, today

from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

from reckon_loyalty.services import members as member_service
from reckon_loyalty.services import points as points_service
from reckon_loyalty.services import rewards as reward_service
from reckon_loyalty.services.utils import require_enabled, require_role


# ---------------------------------------------------------------- members
@frappe.whitelist()
def lookup_member(identifier):
    """Identify a member from a scanned QR code, card number or mobile number."""
    require_role()
    member = member_service.get_member(identifier)
    profile = member_service.member_profile(member)
    profile["rewards"] = [r for r in reward_service.available_rewards(member) if r.get("can_redeem")]
    return profile


@frappe.whitelist(methods=["POST"])
def register_member(member_name, mobile_no, email=None, gender=None, date_of_birth=None, store=None, city=None):
    """Enrol a customer at the till. Returns the new card, or the existing one for a known mobile."""
    require_role()
    require_enabled()
    existing = member_service.get_member(mobile_no, throw=False)
    if existing:
        profile = member_service.member_profile(existing)
        profile["already_registered"] = True
        return profile
    member = member_service.enroll(
        member_name,
        mobile_no,
        channel="POS",
        email=email,
        gender=gender,
        date_of_birth=date_of_birth,
        home_store=_store(store),
        city=city,
    )
    member.reload()
    profile = member_service.member_profile(member)
    profile["already_registered"] = False
    return profile


@frappe.whitelist()
def get_member_history(identifier, limit=10):
    require_role()
    member = member_service.get_member(identifier)
    return {
        "member": member.name,
        "purchases": member_service.purchase_history(member, limit=min(cint(limit) or 10, 50)),
        "points": points_service.get_ledger(member.customer, member.loyalty_program, limit=min(cint(limit) or 10, 50)),
    }


# ---------------------------------------------------------------- rewards
@frappe.whitelist()
def get_rewards(identifier=None):
    require_role()
    member = member_service.get_member(identifier) if identifier else None
    return reward_service.available_rewards(member)


@frappe.whitelist(methods=["POST"])
def redeem_reward(identifier, reward, store=None):
    require_role()
    member = member_service.get_member(identifier)
    result = reward_service.redeem_reward(member.name, reward, store=_store(store))
    result["points_balance"] = points_service.get_balance(member.customer, member.loyalty_program, member.company)
    return result


@frappe.whitelist(methods=["POST"])
def use_voucher(voucher_code, store=None):
    return reward_service.mark_used(voucher_code, store=_store(store))


# ---------------------------------------------------------------- catalogue
@frappe.whitelist()
def get_items(search=None, item_group=None, limit=40):
    """Sellable items with the retail price, for a POS that pulls its catalogue from ERPNext."""
    require_role()
    settings = require_enabled()
    conditions, values = ["i.disabled = 0", "i.is_sales_item = 1", "i.has_variants = 0"], {
        "price_list": settings.price_list,
        "limit": min(cint(limit) or 40, 200),
    }
    if search:
        conditions.append("(i.item_name like %(search)s or i.name like %(search)s)")
        values["search"] = f"%{search}%"
    if item_group:
        bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])
        if bounds:
            conditions.append("ig.lft >= %(lft)s and ig.rgt <= %(rgt)s")
            values.update(lft=bounds[0], rgt=bounds[1])
    return frappe.db.sql(
        f"""
        select i.name as item_code, i.item_name, i.item_group, ip.price_list_rate as rate
        from `tabItem` i
        inner join `tabItem Group` ig on ig.name = i.item_group
        inner join `tabItem Price` ip on ip.item_code = i.name and ip.price_list = %(price_list)s and ip.selling = 1
        where {" and ".join(conditions)}
        order by i.item_group, i.item_name
        limit %(limit)s
        """,
        values,
        as_dict=True,
    )


@frappe.whitelist()
def get_stores():
    require_role()
    return frappe.get_all(
        "Loyalty Store", filters={"is_active": 1}, fields=["name", "store_code", "city", "division"], order_by="name"
    )


# ---------------------------------------------------------------- transactions
@frappe.whitelist(methods=["POST"])
def sync_transaction(**payload):
    """Post one POS sale.

    Body (JSON):
        external_id   POS receipt number. Idempotency key: a repeat returns the first result.
        member        QR payload, card number or mobile number of the member.
        store         Loyalty Store name or store code.
        terminal      Optional till identifier.
        items         [{"item_code", "qty", "rate"?, "discount_percentage"?}]
        redeem_points Optional points to redeem against this sale.
        payments      Optional [{"mode_of_payment", "amount"}]. Defaults to one payment for the amount due.
        posting_date  Optional YYYY-MM-DD (for offline tills that sync later).
    """
    require_role()
    payload = _clean(payload)
    external_id = (payload.get("external_id") or "").strip()
    if not external_id:
        frappe.throw(_("external_id is required."))

    previous = frappe.db.get_value(
        "Loyalty POS Sync Log", {"external_id": external_id}, ["name", "status", "response_payload"], as_dict=True
    )
    if previous and previous.status == "Success":
        response = json.loads(previous.response_payload or "{}")
        response["duplicate"] = True
        return response

    started = time.monotonic()
    frappe.db.savepoint("loyalty_pos_sync")
    try:
        response, invoice, member = _post_sale(payload, external_id)
    except Exception as exc:
        frappe.db.rollback(save_point="loyalty_pos_sync")
        _write_log(previous, external_id, payload, "Failed", started, error=_error_text(exc))
        frappe.db.commit()
        raise

    _write_log(previous, external_id, payload, "Success", started, response=response, invoice=invoice, member=member)
    return response


def _post_sale(payload, external_id):
    settings = require_enabled()
    member = member_service.get_member(payload.get("member"))
    if member.status != "Active":
        frappe.throw(_("Member {0} is {1}.").format(member.member_name, member.status))
    items = payload.get("items") or []
    if not items:
        frappe.throw(_("At least one item is required."))
    store = _store(payload.get("store"))

    invoice = frappe.new_doc("Sales Invoice")
    invoice.update(
        {
            "customer": member.customer,
            "company": settings.company,
            "posting_date": getdate(payload.get("posting_date") or today()),
            "posting_time": payload.get("posting_time") or nowtime(),
            "set_posting_time": 1,
            "is_pos": 1,
            "update_stock": cint(settings.update_stock),
            "selling_price_list": settings.price_list,
            "loyalty_program": member.loyalty_program,
            "loyalty_member": member.name,
            "loyalty_store": store,
            "pos_external_id": external_id,
            "remarks": f"POS {store or ''} {payload.get('terminal') or ''} #{external_id}".strip(),
        }
    )
    if cint(settings.update_stock):
        invoice.set_warehouse = (
            frappe.db.get_value("Loyalty Store", store, "warehouse") if store else None
        ) or settings.default_warehouse
    # No POS Profile is involved: the external POS owns shifts, tills and cash-up.
    invoice.flags.ignore_pos_profile = True

    for row in items:
        if not row.get("item_code") or flt(row.get("qty")) <= 0:
            frappe.throw(_("Each item needs an item_code and a positive qty."))
        rate = row.get("rate")
        if rate is None:
            rate = frappe.db.get_value(
                "Item Price",
                {"item_code": row["item_code"], "price_list": settings.price_list, "selling": 1},
                "price_list_rate",
            )
            if rate is None:
                frappe.throw(
                    _("Item {0} has no price in {1}. Send a rate.").format(row["item_code"], settings.price_list)
                )
        line = {"item_code": row["item_code"], "qty": flt(row["qty"]), "rate": flt(rate), "price_list_rate": flt(rate)}
        if row.get("discount_percentage"):
            line["discount_percentage"] = flt(row["discount_percentage"])
        invoice.append("items", line)

    invoice.flags.ignore_permissions = True
    invoice.set_missing_values()
    invoice.calculate_taxes_and_totals()
    total = flt(invoice.rounded_total) or flt(invoice.grand_total)
    if total <= 0:
        frappe.throw(_("The bill total is zero. Check the item rates."))

    redeem = cint(payload.get("redeem_points"))
    loyalty_amount = 0
    if redeem > 0:
        program = frappe.get_cached_doc("Loyalty Program", member.loyalty_program)
        loyalty_amount = flt(redeem * flt(program.conversion_factor), 2)
        if loyalty_amount > total:
            frappe.throw(_("{0} points are worth more than the bill of {1}.").format(redeem, total))
        invoice.update(
            {
                "redeem_loyalty_points": 1,
                "loyalty_points": redeem,
                "loyalty_amount": loyalty_amount,
                "loyalty_redemption_account": program.expense_account,
                "loyalty_redemption_cost_center": program.cost_center,
            }
        )

    _set_payments(invoice, payload.get("payments"), flt(total - loyalty_amount, 2), settings)
    invoice.insert()
    invoice.submit()

    earned = cint(
        frappe.db.get_value(
            "Loyalty Point Entry",
            {"invoice": invoice.name, "invoice_type": "Sales Invoice", "loyalty_points": [">", 0]},
            "loyalty_points",
        )
    )
    member.reload()
    profile = member_service.member_profile(member)
    response = {
        "external_id": external_id,
        "invoice": invoice.name,
        "member": member.name,
        "member_name": member.member_name,
        "grand_total": total,
        "points_redeemed": redeem,
        "redeemed_amount": loyalty_amount,
        "amount_paid": flt(total - loyalty_amount, 2),
        "points_earned": earned,
        "points_balance": profile["points_balance"],
        "points_value": profile["points_value"],
        "tier": profile["tier"],
        "next_tier": profile["next_tier"],
        "spend_to_next_tier": profile["spend_to_next_tier"],
        "duplicate": False,
    }
    return response, invoice, member


def _set_payments(invoice, payments, amount_due, settings):
    invoice.set("payments", [])
    rows = [row for row in (payments or []) if flt(row.get("amount")) > 0]
    if rows and abs(sum(flt(row["amount"]) for row in rows) - amount_due) > 0.5:
        frappe.throw(
            _("Payments add up to {0} but the amount due is {1}.").format(sum(flt(r["amount"]) for r in rows), amount_due)
        )
    if not rows:
        rows = [{"mode_of_payment": settings.default_mode_of_payment or "Cash", "amount": amount_due}]
    for row in rows:
        mode = row.get("mode_of_payment") or settings.default_mode_of_payment or "Cash"
        account = get_bank_cash_account(mode, invoice.company).get("account")
        invoice.append("payments", {"mode_of_payment": mode, "amount": flt(row["amount"]), "account": account})


@frappe.whitelist(methods=["POST"])
def sync_return(external_id, original_external_id=None, invoice=None):
    """Post a full return of an earlier sale. Earned points are reversed by ERPNext."""
    require_role()
    external_id = (external_id or "").strip()
    if not external_id:
        frappe.throw(_("external_id is required."))
    previous = frappe.db.get_value(
        "Loyalty POS Sync Log", {"external_id": external_id}, ["name", "status", "response_payload"], as_dict=True
    )
    if previous and previous.status == "Success":
        response = json.loads(previous.response_payload or "{}")
        response["duplicate"] = True
        return response

    payload = {"external_id": external_id, "original_external_id": original_external_id, "invoice": invoice}
    started = time.monotonic()
    frappe.db.savepoint("loyalty_pos_sync")
    try:
        original = invoice or frappe.db.get_value(
            "Sales Invoice", {"pos_external_id": original_external_id, "docstatus": 1, "is_return": 0}
        )
        if not original:
            frappe.throw(_("Original sale {0} was not found.").format(original_external_id or invoice))

        from erpnext.controllers.sales_and_purchase_return import make_return_doc

        credit_note = make_return_doc("Sales Invoice", original)
        credit_note.pos_external_id = external_id
        credit_note.flags.ignore_permissions = True
        credit_note.flags.ignore_pos_profile = True
        credit_note.insert()
        credit_note.submit()

        member_name = credit_note.get("loyalty_member") or frappe.db.get_value(
            "Loyalty Member", {"customer": credit_note.customer}
        )
        member = frappe.get_doc("Loyalty Member", member_name) if member_name else None
        response = {
            "external_id": external_id,
            "credit_note": credit_note.name,
            "return_against": original,
            "grand_total": flt(credit_note.grand_total),
            "duplicate": False,
        }
        if member:
            member_service.refresh_member_stats(member.name)
            member.reload()
            profile = member_service.member_profile(member)
            response.update(points_balance=profile["points_balance"], tier=profile["tier"], member=member.name)
    except Exception as exc:
        frappe.db.rollback(save_point="loyalty_pos_sync")
        _write_log(previous, external_id, payload, "Failed", started, error=_error_text(exc), kind="Return")
        frappe.db.commit()
        raise

    _write_log(
        previous, external_id, payload, "Success", started, response=response, invoice=credit_note, member=member, kind="Return"
    )
    return response


# ---------------------------------------------------------------- helpers
def _clean(payload):
    payload = {key: value for key, value in payload.items() if key != "cmd"}
    for key in ("items", "payments"):
        if isinstance(payload.get(key), str):
            payload[key] = json.loads(payload[key])
    return payload


def _store(store):
    if not store:
        return None
    if frappe.db.exists("Loyalty Store", store):
        return store
    name = frappe.db.get_value("Loyalty Store", {"store_code": store})
    if not name:
        frappe.throw(_("Store {0} was not found.").format(store))
    return name


def _error_text(exc):
    messages = [frappe.utils.strip_html(str(m)) for m in (frappe.local.message_log or [])]
    text = str(exc) or (messages[-1] if messages else exc.__class__.__name__)
    return frappe.utils.strip_html(text)[:1000]


def _write_log(previous, external_id, payload, status, started, response=None, invoice=None, member=None, error=None, kind="Sale"):
    log = frappe.get_doc("Loyalty POS Sync Log", previous.name) if previous else frappe.new_doc("Loyalty POS Sync Log")
    log.update(
        {
            "external_id": external_id,
            "transaction_type": kind,
            "status": status,
            "store": invoice.get("loyalty_store") if invoice else None,
            "terminal": payload.get("terminal"),
            "member": member.name if member else None,
            "sales_invoice": invoice.name if invoice else None,
            "grand_total": flt(invoice.grand_total) if invoice else 0,
            "points_earned": cint((response or {}).get("points_earned")),
            "points_redeemed": cint((response or {}).get("points_redeemed")),
            "processing_ms": int((time.monotonic() - started) * 1000),
            "company": invoice.company if invoice else None,
            "request_payload": json.dumps(payload, indent=1, default=str),
            "response_payload": json.dumps(response, indent=1, default=str) if response else None,
            "error": error,
        }
    )
    log.flags.ignore_permissions = True
    log.save()
