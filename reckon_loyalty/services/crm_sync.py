"""Optional bridge to Frappe CRM.

Retail members are ERPNext Customers. Frappe CRM is used for the people a team has to
work one by one: new web and app sign-ups, and segments handed to clienteling or the
call centre (for example lapsed Platinum members). Each becomes a CRM Lead.
"""

import frappe
from frappe import _

from reckon_loyalty.services import segments as segment_service
from reckon_loyalty.services.utils import get_settings, require_role

MANAGERS = ("Loyalty Manager", "System Manager")


def crm_installed():
    return "crm" in frappe.get_installed_apps() and frappe.db.exists("DocType", "CRM Lead")


def create_lead_for_member(member, source=None, throw=False):
    """Create a CRM Lead for a member once. Never blocks enrolment unless throw is set."""
    if not crm_installed():
        if throw:
            frappe.throw(_("Frappe CRM is not installed on this site."))
        return None
    doc = frappe.get_doc("Loyalty Member", member) if isinstance(member, str) else member
    if doc.crm_lead and frappe.db.exists("CRM Lead", doc.crm_lead):
        return doc.crm_lead

    source = source or get_settings().crm_lead_source or "Loyalty Signup"
    if not frappe.db.exists("CRM Lead Source", source):
        frappe.get_doc({"doctype": "CRM Lead Source", "source_name": source}).insert(ignore_permissions=True)

    first, _sep, last = doc.member_name.partition(" ")
    lead = frappe.new_doc("CRM Lead")
    lead.update(
        {
            "first_name": first,
            "last_name": last or None,
            "mobile_no": doc.mobile_no,
            "email": doc.email,
            "source": source,
        }
    )
    if lead.meta.has_field("company"):
        lead.company = doc.company
    if lead.meta.has_field("gender") and doc.gender and frappe.db.exists("Gender", doc.gender):
        lead.gender = doc.gender
    lead.flags.ignore_permissions = True
    try:
        lead.insert()
    except Exception:
        if throw:
            raise
        frappe.log_error(title=f"Loyalty: CRM Lead not created for {doc.name}")
        return None
    lead.add_comment(
        "Comment",
        _("Loyalty member {0}, card {1}, tier {2}, lifetime spend {3}.").format(
            doc.member_name, doc.card_number, doc.tier or "-", frappe.format_value(doc.lifetime_spend, {"fieldtype": "Currency"})
        ),
    )
    frappe.db.set_value("Loyalty Member", doc.name, "crm_lead", lead.name, update_modified=False)
    return lead.name


@frappe.whitelist()
def create_lead(member):
    require_role(MANAGERS)
    return create_lead_for_member(member, throw=True)


@frappe.whitelist()
def push_segment(segment, limit=50):
    """Hand the top members of a segment to the CRM team as leads."""
    require_role(MANAGERS)
    if not crm_installed():
        frappe.throw(_("Frappe CRM is not installed on this site."))
    created, skipped = [], 0
    for member in segment_service.get_members(segment, limit=min(int(limit), 200)):
        if frappe.db.get_value("Loyalty Member", member.name, "crm_lead"):
            skipped += 1
            continue
        lead = create_lead_for_member(member.name, source=f"Segment: {segment}"[:140])
        if lead:
            created.append(lead)
        else:
            skipped += 1
    return {"created": len(created), "skipped": skipped, "leads": created[:20]}
