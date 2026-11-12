import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, strip_html

from reckon_loyalty.services import members as member_service
from reckon_loyalty.services import points as points_service
from reckon_loyalty.services import segments as segment_service
from reckon_loyalty.services.utils import card_url, get_settings, require_role

INLINE_LIMIT = 300
MANAGERS = ("Loyalty Manager", "System Manager")


# ---------------------------------------------------------------- delivery
def _deliver_sms(mobile, text):
    """Returns (status, error). In demo mode nothing leaves the server."""
    if cint(get_settings().demo_mode):
        return "Simulated", None
    try:
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        send_sms(receiver_list=[mobile], msg=text, success_msg=False)
        return "Sent", None
    except Exception as exc:
        return "Failed", str(exc)[:500]


def _deliver_email(email, subject, body, campaign=None):
    if cint(get_settings().demo_mode):
        return "Simulated", None
    try:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=body,
            reference_doctype="Loyalty Campaign" if campaign else None,
            reference_name=campaign,
        )
        return "Sent", None
    except Exception as exc:
        return "Failed", str(exc)[:500]


def _log(member, channel, recipient, status, message, subject=None, campaign=None, error=None, company=None):
    frappe.get_doc(
        {
            "doctype": "Loyalty Message Log",
            "member": member,
            "campaign": campaign,
            "channel": channel,
            "recipient": recipient,
            "status": status,
            "subject": subject,
            "message": message,
            "error": error,
            "sent_on": now_datetime(),
            "company": company,
        }
    ).insert(ignore_permissions=True)


def _context(member, campaign=None):
    name = member.get("member_name") or ""
    return {
        "member_name": name,
        "first_name": name.split(" ")[0],
        "tier": member.get("tier") or "",
        "points_balance": cint(member.get("points_balance")),
        "card_number": member.get("card_number"),
        "card_url": card_url(member.get("qr_token")),
        "offer_code": campaign.offer_code if campaign else "",
        "brand": get_settings().brand_name or "",
    }


def send_welcome(member):
    """Text the digital card link to a new member."""
    if not cint(member.sms_opt_in):
        return
    settings = get_settings()
    context = _context(member.as_dict())
    text = _("Welcome to {0}, {1}! Your digital member card: {2}").format(
        settings.brand_name or _("our loyalty club"), context["first_name"], context["card_url"]
    )
    status, error = _deliver_sms(member.mobile_no, text)
    _log(member.name, "SMS", member.mobile_no, status, text, error=error, company=member.company)


# ---------------------------------------------------------------- campaign actions
@frappe.whitelist()
def send_now(campaign):
    require_role(MANAGERS)
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    if doc.status in ("Sending", "Sent"):
        frappe.throw(_("Campaign {0} is already {1}.").format(doc.name, doc.status))
    _validate_content(doc)
    size = segment_service.summarise(doc.segment)["members"]
    if not size:
        frappe.throw(_("Segment {0} has no members right now.").format(doc.segment))
    doc.db_set("status", "Sending")
    if size <= INLINE_LIMIT:
        return dispatch(doc.name)
    frappe.enqueue("reckon_loyalty.services.campaigns.dispatch", queue="long", timeout=3600, campaign=doc.name)
    return {"queued": True, "targeted": size}


@frappe.whitelist()
def schedule(campaign):
    require_role(MANAGERS)
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    if doc.status not in ("Draft", "Cancelled"):
        frappe.throw(_("Only a Draft campaign can be scheduled."))
    if not doc.scheduled_at or get_datetime(doc.scheduled_at) <= now_datetime():
        frappe.throw(_("Set Schedule For to a time in the future."))
    _validate_content(doc)
    doc.db_set("status", "Scheduled")


@frappe.whitelist()
def cancel_schedule(campaign):
    require_role(MANAGERS)
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    if doc.status != "Scheduled":
        frappe.throw(_("Only a Scheduled campaign can be cancelled."))
    doc.db_set("status", "Draft")


@frappe.whitelist()
def preview_message(campaign):
    """Render the campaign for the first member of the segment."""
    require_role()
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    sample = segment_service.get_members(doc.segment, limit=1)
    if not sample:
        frappe.throw(_("Segment {0} has no members right now.").format(doc.segment))
    context = _context(sample[0], doc)
    return {
        "member": sample[0].member_name,
        "sms": frappe.render_template(doc.sms_message or "", context),
        "email_subject": frappe.render_template(doc.email_subject or "", context),
        "email_message": frappe.render_template(doc.email_message or "", context),
    }


def _validate_content(doc):
    if doc.channel != "Email" and not (doc.sms_message or "").strip():
        frappe.throw(_("Write the SMS text first."))
    if doc.channel != "SMS" and not ((doc.email_subject or "").strip() and strip_html(doc.email_message or "").strip()):
        frappe.throw(_("Write the email subject and body first."))


def send_due_campaigns():
    due = frappe.get_all(
        "Loyalty Campaign", filters={"status": "Scheduled", "scheduled_at": ["<=", now_datetime()]}, pluck="name"
    )
    for name in due:
        frappe.db.set_value("Loyalty Campaign", name, "status", "Sending")
        frappe.db.commit()
        dispatch(name)


def dispatch(campaign):
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    recipients = segment_service.get_members(doc.segment)
    counts = {"sms": 0, "email": 0, "failed": 0, "bonus": 0}

    for member in recipients:
        context = _context(member, doc)
        if doc.channel in ("SMS", "SMS and Email"):
            text = frappe.render_template(doc.sms_message or "", context)
            if not cint(member.sms_opt_in):
                status, error = "Skipped", "No SMS consent"
            else:
                status, error = _deliver_sms(member.mobile_no, text)
            _log(member.name, "SMS", member.mobile_no, status, text, campaign=doc.name, error=error, company=doc.company)
            counts["sms" if status in ("Sent", "Simulated") else "failed"] += 1

        if doc.channel in ("Email", "SMS and Email"):
            subject = frappe.render_template(doc.email_subject or "", context)
            body = frappe.render_template(doc.email_message or "", context)
            if not member.email or not cint(member.email_opt_in):
                status, error = "Skipped", "No email address or consent"
            else:
                status, error = _deliver_email(member.email, subject, body, campaign=doc.name)
            _log(
                member.name,
                "Email",
                member.email,
                status,
                strip_html(body)[:500],
                subject=subject,
                campaign=doc.name,
                error=error,
                company=doc.company,
            )
            counts["email" if status in ("Sent", "Simulated") else "failed"] += 1

        if cint(doc.bonus_points):
            points_service.add_points(member.name, doc.bonus_points, f"Campaign bonus: {doc.name}")
            member_service.refresh_member_stats(member.name)
            counts["bonus"] += cint(doc.bonus_points)

    doc.db_set(
        {
            "status": "Sent",
            "sent_on": now_datetime(),
            "targeted": len(recipients),
            "sms_sent": counts["sms"],
            "email_sent": counts["email"],
            "failed": counts["failed"],
            "bonus_points_issued": counts["bonus"],
        }
    )
    frappe.db.commit()
    return {"targeted": len(recipients), **counts, "demo_mode": cint(get_settings().demo_mode)}


@frappe.whitelist()
def refresh_results(campaign):
    """Sales by targeted members inside the offer window."""
    require_role()
    doc = frappe.get_doc("Loyalty Campaign", campaign)
    if doc.status != "Sent":
        return {}
    start = getdate(doc.start_date or doc.sent_on)
    end = getdate(doc.end_date or add_days(start, 14))
    row = frappe.db.sql(
        """
        select count(*) as orders, coalesce(sum(si.base_grand_total), 0) as revenue
        from `tabSales Invoice` si
        where si.docstatus = 1 and si.is_return = 0 and si.posting_date between %s and %s
            and si.customer in (
                select m.customer from `tabLoyalty Message Log` l
                inner join `tabLoyalty Member` m on m.name = l.member
                where l.campaign = %s and l.status in ('Sent', 'Simulated')
            )
        """,
        (start, end, doc.name),
        as_dict=True,
    )[0]
    doc.db_set({"attributed_orders": cint(row.orders), "attributed_revenue": row.revenue})
    return {"orders": cint(row.orders), "revenue": row.revenue, "from": start, "to": end}
