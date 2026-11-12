import frappe
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, today

from reckon_loyalty.services.utils import get_settings, require_role, tier_rules


@frappe.whitelist()
def get_data(from_date=None, to_date=None, store=None):
    """One call that feeds the whole management dashboard."""
    require_role(("Loyalty Manager", "Loyalty User", "System Manager"))
    settings = get_settings()
    company, program = settings.company, settings.loyalty_program
    to_date = getdate(to_date or today())
    from_date = getdate(from_date or add_days(to_date, -89))
    has_store = frappe.get_meta("Sales Invoice").has_field("loyalty_store")

    params = {"company": company, "program": program, "from": from_date, "to": to_date, "store": store, "today": today()}
    member_join = "inner join `tabLoyalty Member` m on m.customer = si.customer"
    store_rule = "and si.loyalty_store = %(store)s" if store and has_store else ""
    member_store_rule = "and m.home_store = %(store)s" if store else ""
    sale_rule = f"si.docstatus = 1 and si.company = %(company)s and si.posting_date between %(from)s and %(to)s {store_rule}"

    def one(sql):
        return frappe.db.sql(sql, params, as_dict=True)[0]

    def rows(sql):
        return frappe.db.sql(sql, params, as_dict=True)

    members = one(
        f"""select count(*) as total,
                sum(case when m.enrollment_date between %(from)s and %(to)s then 1 else 0 end) as new_members,
                sum(case when m.total_orders > 1 then 1 else 0 end) as repeat_buyers,
                sum(case when m.total_orders > 0 then 1 else 0 end) as buyers,
                coalesce(sum(m.points_balance), 0) as outstanding_points,
                coalesce(sum(m.points_expiring_30d), 0) as expiring_points
            from `tabLoyalty Member` m where m.company = %(company)s {member_store_rule}"""
    )
    sales = one(
        f"""select count(distinct case when si.is_return = 0 then si.name end) as orders,
                count(distinct si.customer) as active_members,
                coalesce(sum(si.base_grand_total), 0) as revenue
            from `tabSales Invoice` si {member_join} where {sale_rule}"""
    )
    point_rule = "e.company = %(company)s and e.loyalty_program = %(program)s and e.posting_date between %(from)s and %(to)s"
    points = one(
        f"""select coalesce(sum(case when e.loyalty_points > 0 then e.loyalty_points end), 0) as issued,
                coalesce(-sum(case when e.loyalty_points < 0 then e.loyalty_points end), 0) as redeemed
            from `tabLoyalty Point Entry` e where {point_rule}"""
    )
    conversion = flt(frappe.db.get_value("Loyalty Program", program, "conversion_factor")) if program else 0

    kpis = {
        "members": cint(members.total),
        "new_members": cint(members.new_members),
        "active_members": cint(sales.active_members),
        "active_rate": _pct(sales.active_members, members.total),
        "repeat_rate": _pct(members.repeat_buyers, members.buyers),
        "revenue": flt(sales.revenue),
        "orders": cint(sales.orders),
        "avg_basket": flt(sales.revenue) / sales.orders if sales.orders else 0,
        "points_issued": cint(points.issued),
        "points_redeemed": cint(points.redeemed),
        "redemption_rate": _pct(points.redeemed, points.issued),
        "outstanding_points": cint(members.outstanding_points),
        "points_liability": flt(members.outstanding_points) * conversion,
        "expiring_points": cint(members.expiring_points),
    }

    tier_counts = {
        row.tier: row
        for row in rows(
            f"""select coalesce(m.tier, 'No tier') as tier, count(*) as members,
                    coalesce(sum(m.lifetime_spend), 0) as spend
                from `tabLoyalty Member` m where m.company = %(company)s {member_store_rule} group by m.tier"""
        )
    }
    tiers = [
        {
            "tier": rule.tier_name,
            "color": rule.card_color,
            "members": cint(tier_counts.get(rule.tier_name, {}).get("members")),
            "spend": flt(tier_counts.get(rule.tier_name, {}).get("spend")),
        }
        for rule in tier_rules(program)
    ]

    months_start = get_first_day(add_months(to_date, -5))
    params["months_start"] = months_start
    month_keys = [add_months(months_start, index).strftime("%Y-%m") for index in range(6)]
    enrolled = {
        row.month: row.members
        for row in rows(
            f"""select date_format(m.enrollment_date, '%%Y-%%m') as month, count(*) as members
                from `tabLoyalty Member` m
                where m.company = %(company)s and m.enrollment_date >= %(months_start)s {member_store_rule}
                group by month"""
        )
    }
    monthly_sales = {
        row.month: row
        for row in rows(
            f"""select date_format(si.posting_date, '%%Y-%%m') as month, coalesce(sum(si.base_grand_total), 0) as revenue,
                    count(distinct si.customer) as buyers
                from `tabSales Invoice` si {member_join}
                where si.docstatus = 1 and si.company = %(company)s and si.posting_date >= %(months_start)s {store_rule}
                group by month"""
        )
    }
    trend = [
        {
            "month": key,
            "new_members": cint(enrolled.get(key)),
            "revenue": flt(monthly_sales.get(key, {}).get("revenue")),
            "buyers": cint(monthly_sales.get(key, {}).get("buyers")),
        }
        for key in month_keys
    ]

    stores = (
        rows(
            f"""select coalesce(si.loyalty_store, 'Unassigned') as store, coalesce(sum(si.base_grand_total), 0) as revenue,
                    count(distinct case when si.is_return = 0 then si.name end) as orders,
                    count(distinct si.customer) as members
                from `tabSales Invoice` si {member_join} where {sale_rule}
                group by si.loyalty_store order by revenue desc limit 12"""
        )
        if has_store
        else []
    )
    categories = rows(
        f"""select sii.item_group as category, coalesce(sum(sii.base_net_amount), 0) as revenue, sum(sii.qty) as qty
            from `tabSales Invoice Item` sii
            inner join `tabSales Invoice` si on si.name = sii.parent
            {member_join}
            where {sale_rule}
            group by sii.item_group order by revenue desc limit 10"""
    )
    behaviour = rows(
        f"""select coalesce(m.rfm_segment, 'No Purchase') as segment, count(*) as members,
                coalesce(sum(m.lifetime_spend), 0) as spend
            from `tabLoyalty Member` m where m.company = %(company)s {member_store_rule}
            group by m.rfm_segment order by members desc"""
    )
    top_members = rows(
        f"""select m.name, m.member_name, m.tier, m.home_store, coalesce(sum(si.base_grand_total), 0) as revenue,
                count(distinct case when si.is_return = 0 then si.name end) as orders, m.points_balance
            from `tabSales Invoice` si {member_join} where {sale_rule}
            group by m.name order by revenue desc limit 10"""
    )
    campaigns = frappe.get_all(
        "Loyalty Campaign",
        filters={"company": company} if company else {},
        fields=["name", "segment", "channel", "status", "targeted", "sms_sent", "email_sent", "failed",
                "attributed_orders", "attributed_revenue", "sent_on"],
        order_by="modified desc",
        limit=8,
    )
    segments = frappe.get_all(
        "Loyalty Segment",
        filters={"is_active": 1},
        fields=["name", "member_count", "total_spend", "description"],
        order_by="member_count desc",
        limit=10,
    )
    sync = one(
        """select count(*) as total, sum(case when status = 'Success' then 1 else 0 end) as success,
                sum(case when status = 'Failed' then 1 else 0 end) as failed,
                coalesce(round(avg(case when status = 'Success' then processing_ms end)), 0) as avg_ms
            from `tabLoyalty POS Sync Log` where date(creation) between %(from)s and %(to)s"""
    )

    return {
        "brand": settings.brand_name,
        "currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
        "from_date": from_date,
        "to_date": to_date,
        "kpis": kpis,
        "tiers": tiers,
        "trend": trend,
        "stores": stores,
        "categories": categories,
        "behaviour": behaviour,
        "top_members": top_members,
        "campaigns": campaigns,
        "segments": segments,
        "pos_sync": {key: cint(value) for key, value in sync.items()},
        "demo_mode": cint(settings.demo_mode),
    }


def _pct(part, whole):
    return round(flt(part) / flt(whole) * 100, 1) if flt(whole) else 0
