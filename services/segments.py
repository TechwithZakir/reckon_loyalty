"""Rule-based segments over Loyalty Member.

Behaviour rules read the statistics cached on the member (refreshed on every invoice
and nightly), so a segment of any size is one indexed query.
"""

import calendar

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from reckon_loyalty.services.utils import require_role

MEMBER_FIELDS = (
    "m.name, m.member_name, m.mobile_no, m.email, m.tier, m.points_balance, m.lifetime_spend, "
    "m.total_orders, m.last_purchase_date, m.home_store, m.city, m.sms_opt_in, m.email_opt_in, "
    "m.card_number, m.qr_token, m.customer, m.rfm_segment"
)


def _where(segment):
    conditions, values = ["m.status = 'Active'"], {}

    def add(sql, **params):
        conditions.append(sql)
        values.update(params)

    if segment.company:
        add("m.company = %(company)s", company=segment.company)
    tiers = [tier.strip() for tier in (segment.tiers or "").split(",") if tier.strip()]
    if tiers:
        add("m.tier in %(tiers)s", tiers=tiers)
    if segment.gender:
        add("m.gender = %(gender)s", gender=segment.gender)
    if segment.home_store:
        add("m.home_store = %(home_store)s", home_store=segment.home_store)
    if segment.city:
        add("m.city = %(city)s", city=segment.city)
    if segment.rfm_segment:
        add("m.rfm_segment = %(rfm)s", rfm=segment.rfm_segment)
    if cint(segment.enrolled_within_days):
        add("m.enrollment_date >= %(enrolled_from)s", enrolled_from=add_days(today(), -cint(segment.enrolled_within_days)))
    if segment.birthday_month:
        month = _month_number(segment.birthday_month)
        add("month(m.date_of_birth) = %(birth_month)s", birth_month=month)

    if flt(segment.min_lifetime_spend):
        add("m.lifetime_spend >= %(min_spend)s", min_spend=flt(segment.min_lifetime_spend))
    if flt(segment.max_lifetime_spend):
        add("m.lifetime_spend <= %(max_spend)s", max_spend=flt(segment.max_lifetime_spend))
    if cint(segment.min_orders):
        add("m.total_orders >= %(min_orders)s", min_orders=cint(segment.min_orders))
    if cint(segment.max_orders):
        add("m.total_orders <= %(max_orders)s", max_orders=cint(segment.max_orders))
    if cint(segment.min_points_balance):
        add("m.points_balance >= %(min_points)s", min_points=cint(segment.min_points_balance))
    if cint(segment.purchased_within_days):
        add("m.last_purchase_date >= %(bought_from)s", bought_from=add_days(today(), -cint(segment.purchased_within_days)))
    if cint(segment.not_purchased_in_days):
        add(
            "m.total_orders > 0 and m.last_purchase_date < %(lapsed_before)s",
            lapsed_before=add_days(today(), -cint(segment.not_purchased_in_days)),
        )

    if segment.item_group:
        bounds = frappe.db.get_value("Item Group", segment.item_group, ["lft", "rgt"])
        if bounds:
            date_rule = ""
            if cint(segment.item_group_within_days):
                date_rule = "and si.posting_date >= %(group_from)s"
                values["group_from"] = add_days(today(), -cint(segment.item_group_within_days))
            add(
                f"""exists (
                    select 1 from `tabSales Invoice Item` sii
                    inner join `tabSales Invoice` si on si.name = sii.parent
                    inner join `tabItem Group` ig on ig.name = sii.item_group
                    where si.customer = m.customer and si.docstatus = 1 and si.is_return = 0
                        and ig.lft >= %(group_lft)s and ig.rgt <= %(group_rgt)s {date_rule}
                )""",
                group_lft=bounds[0],
                group_rgt=bounds[1],
            )

    if cint(segment.require_sms_opt_in):
        conditions.append("m.sms_opt_in = 1")
    if cint(segment.require_email_opt_in):
        conditions.append("m.email_opt_in = 1 and coalesce(m.email, '') != ''")
    return " and ".join(conditions), values


def _month_number(label):
    current = getdate(today()).month
    if label == "This Month":
        return current
    if label == "Next Month":
        return current % 12 + 1
    return list(calendar.month_name).index(label)


def get_members(segment, limit=None):
    if isinstance(segment, str):
        segment = frappe.get_doc("Loyalty Segment", segment)
    where, values = _where(segment)
    limit_sql = f"limit {cint(limit)}" if limit else ""
    return frappe.db.sql(
        f"select {MEMBER_FIELDS} from `tabLoyalty Member` m where {where} "
        f"order by m.lifetime_spend desc {limit_sql}",
        values,
        as_dict=True,
    )


def summarise(segment):
    if isinstance(segment, str):
        segment = frappe.get_doc("Loyalty Segment", segment)
    where, values = _where(segment)
    row = frappe.db.sql(
        f"""select count(*) as members, coalesce(sum(m.lifetime_spend), 0) as spend,
                coalesce(sum(m.points_balance), 0) as points,
                sum(case when m.sms_opt_in = 1 then 1 else 0 end) as sms_reachable,
                sum(case when m.email_opt_in = 1 and coalesce(m.email, '') != '' then 1 else 0 end) as email_reachable
            from `tabLoyalty Member` m where {where}""",
        values,
        as_dict=True,
    )[0]
    return {key: (flt(value) if key == "spend" else cint(value)) for key, value in row.items()}


def refresh_segment(name):
    summary = summarise(name)
    frappe.db.set_value(
        "Loyalty Segment",
        name,
        {"member_count": summary["members"], "total_spend": summary["spend"], "last_refreshed": now_datetime()},
        update_modified=False,
    )
    return summary


def refresh_all_segments():
    for name in frappe.get_all("Loyalty Segment", filters={"is_active": 1}, pluck="name"):
        refresh_segment(name)
    frappe.db.commit()


@frappe.whitelist()
def preview(segment, save=1):
    """Size of the segment and its top members. Accepts an unsaved form too."""
    require_role()
    if isinstance(segment, str) and segment.strip().startswith("{"):
        doc = frappe.get_doc(frappe.parse_json(segment))
    else:
        doc = frappe.get_doc("Loyalty Segment", segment)
        if cint(save):
            refresh_segment(doc.name)
    return {"summary": summarise(doc), "members": get_members(doc, limit=25)}
