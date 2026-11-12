"""Seeds a complete, self-contained demo company.

    bench --site <site> execute reckon_loyalty.demo.seed.run

Everything lives under its own Company ("Sailor (Demo)"), customer group, item group and
price list, so it can sit beside other companies on a shared site. The run is idempotent:
masters are skipped when they exist and sales are only generated once.
"""

import random

import frappe
from frappe.utils import add_days, add_months, cint, date_diff, getdate, today

from reckon_loyalty.demo import catalog as C

SALE_PREFIX = "SLR-DEMO-"


def run(members=60, months=6, force_sales=0):
    if frappe.session.user != "Administrator":
        frappe.throw("Run the demo seeder from bench (as Administrator).")
    frappe.flags.mute_emails = True
    rng = random.Random(2026)

    company = _company()
    _item_groups()
    _price_list()
    _items(company)
    _customer_group()
    stores = _stores(company)
    program = _program(company)
    _settings(company, program)
    _fiscal_years(company, cint(months))
    _repair_company(company, program)
    frappe.db.commit()

    member_names = _members(rng, cint(members), cint(months), stores)
    frappe.db.commit()
    if cint(force_sales) or not frappe.db.exists("Sales Invoice", {"pos_external_id": ["like", f"{SALE_PREFIX}%"]}):
        _sales(rng, member_names, cint(months))
    _rewards(company, rng)
    _segments(company)
    _campaigns(company)

    from reckon_loyalty.services.members import refresh_all_members
    from reckon_loyalty.services.segments import refresh_all_segments

    refresh_all_members()
    refresh_all_segments()
    frappe.db.commit()
    summary = {
        "company": company,
        "members": frappe.db.count("Loyalty Member", {"company": company}),
        "invoices": frappe.db.count("Sales Invoice", {"company": company, "docstatus": 1}),
        "point_entries": frappe.db.count("Loyalty Point Entry", {"company": company}),
        "tiers": dict(
            frappe.db.sql("select tier, count(*) from `tabLoyalty Member` where company = %s group by tier", company)
        ),
    }
    print(summary)
    return summary


# ---------------------------------------------------------------- masters
def _company():
    if frappe.db.exists("Company", C.COMPANY):
        return C.COMPANY
    doc = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": C.COMPANY,
            "abbr": C.ABBR,
            "default_currency": "BDT",
            "country": "Bangladesh",
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": "Standard",
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _scope(doc, company):
    """Sites running the Reckon SaaS apps scope shared masters to a company with this field."""
    if doc.meta.has_field("rd_company"):
        doc.rd_company = company


def _tree_root(doctype, parent_field):
    return frappe.db.sql(
        f"select name from `tab{doctype}` where is_group = 1 and ifnull({parent_field}, '') = '' order by lft limit 1"
    )[0][0]


def _item_groups():
    root = _tree_root("Item Group", "parent_item_group")
    if not frappe.db.exists("Item Group", C.ROOT_GROUP):
        frappe.get_doc(
            {"doctype": "Item Group", "item_group_name": C.ROOT_GROUP, "parent_item_group": root, "is_group": 1}
        ).insert(ignore_permissions=True)
    for group in C.ITEMS:
        if not frappe.db.exists("Item Group", group):
            frappe.get_doc(
                {"doctype": "Item Group", "item_group_name": group, "parent_item_group": C.ROOT_GROUP, "is_group": 0}
            ).insert(ignore_permissions=True)


def _price_list():
    if not frappe.db.exists("Price List", C.PRICE_LIST):
        doc = frappe.get_doc(
            {"doctype": "Price List", "price_list_name": C.PRICE_LIST, "currency": "BDT", "selling": 1, "enabled": 1}
        )
        _scope(doc, C.COMPANY)
        doc.insert(ignore_permissions=True)


def _items(company):
    for group, rows in C.ITEMS.items():
        for code, name, price in rows:
            if not frappe.db.exists("Item", code):
                item = frappe.get_doc(
                    {
                        "doctype": "Item",
                        "item_code": code,
                        "item_name": name,
                        "description": name,
                        "item_group": group,
                        "stock_uom": "Nos",
                        "is_stock_item": 0,
                        "is_sales_item": 1,
                        "brand": C.BRAND if frappe.db.exists("Brand", C.BRAND) else None,
                    }
                )
                _scope(item, company)
                item.insert(ignore_permissions=True)
            if not frappe.db.exists("Item Price", {"item_code": code, "price_list": C.PRICE_LIST}):
                price_doc = frappe.get_doc(
                    {"doctype": "Item Price", "item_code": code, "price_list": C.PRICE_LIST, "price_list_rate": price, "selling": 1}
                )
                _scope(price_doc, company)
                price_doc.insert(ignore_permissions=True)


def _customer_group():
    if not frappe.db.exists("Customer Group", C.CUSTOMER_GROUP):
        root = _tree_root("Customer Group", "parent_customer_group")
        frappe.get_doc(
            {"doctype": "Customer Group", "customer_group_name": C.CUSTOMER_GROUP, "parent_customer_group": root, "is_group": 0}
        ).insert(ignore_permissions=True)


def _stores(company):
    for name, code, division, city, phone, address, hours in C.STORES:
        if not frappe.db.exists("Loyalty Store", name):
            frappe.get_doc(
                {
                    "doctype": "Loyalty Store",
                    "store_name": name,
                    "store_code": code,
                    "company": company,
                    "division": division,
                    "city": city,
                    "phone": phone,
                    "address": address,
                    "business_hours": hours,
                }
            ).insert(ignore_permissions=True)
    return [row[0] for row in C.STORES]


def _program(company):
    if frappe.db.exists("Loyalty Program", C.PROGRAM):
        return C.PROGRAM
    abbr = frappe.get_cached_value("Company", company, "abbr")
    expense = (
        frappe.db.get_value("Account", {"company": company, "account_name": "Marketing Expenses", "is_group": 0})
        or frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0})
    )
    cost_center = frappe.get_cached_value("Company", company, "cost_center") or f"Main - {abbr}"
    doc = frappe.get_doc(
        {
            "doctype": "Loyalty Program",
            "loyalty_program_name": C.PROGRAM,
            "loyalty_program_type": "Multiple Tier Program",
            "from_date": add_months(today(), -12),
            "company": company,
            "customer_group": C.CUSTOMER_GROUP,
            # Never auto opt-in: ERPNext applies that across every company on the site.
            "auto_opt_in": 0,
            "conversion_factor": 1,
            "expiry_duration": 365,
            "expense_account": expense,
            "cost_center": cost_center,
            "collection_rules": [
                {"tier_name": tier, "min_spent": minimum, "collection_factor": factor}
                for tier, minimum, factor, _color, _benefits in C.TIERS
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _settings(company, program):
    settings = frappe.get_single("Loyalty Settings")
    settings.update(
        {
            "enabled": 1,
            "demo_mode": 1,
            "brand_name": C.BRAND,
            "brand_color": "#111827",
            "company": company,
            "loyalty_program": program,
            "card_prefix": C.ABBR,
            "customer_group": C.CUSTOMER_GROUP,
            "territory": "Bangladesh" if frappe.db.exists("Territory", "Bangladesh") else None,
            "price_list": C.PRICE_LIST,
            "welcome_bonus_points": 100,
            "birthday_bonus_points": 250,
            "default_mode_of_payment": "Cash",
            "update_stock": 0,
            "default_warehouse": None,
            "create_crm_lead": 1,
            "crm_lead_source": "Loyalty Signup",
        }
    )
    settings.set(
        "tiers",
        [{"tier_name": tier, "card_color": color, "benefits": benefits} for tier, _min, _factor, color, benefits in C.TIERS],
    )
    settings.save(ignore_permissions=True)
    frappe.clear_document_cache("Loyalty Settings", "Loyalty Settings")

    # A new company's Cash account must be mapped on the Cash mode of payment for POS sales.
    mode = frappe.get_doc("Mode of Payment", "Cash")
    if not any(row.company == company for row in mode.accounts):
        cash = frappe.get_cached_value("Company", company, "default_cash_account") or frappe.db.get_value(
            "Account", {"company": company, "account_type": "Cash", "is_group": 0}
        )
        mode.append("accounts", {"company": company, "default_account": cash})
        mode.save(ignore_permissions=True)


def _fiscal_years(company, months):
    """A fiscal year that lists companies only applies to those: add the demo company where needed."""
    start = add_days(today(), -(months * 30 + 5))
    years = frappe.get_all(
        "Fiscal Year",
        filters={"disabled": 0, "year_end_date": [">=", start], "year_start_date": ["<=", today()]},
        pluck="name",
    )
    for name in years:
        doc = frappe.get_doc("Fiscal Year", name)
        if doc.companies and not any(row.company == company for row in doc.companies):
            doc.append("companies", {"company": company})
            doc.save(ignore_permissions=True)


def _repair_company(company, program):
    """Move demo members that an earlier run stamped with the user's default company."""
    wrong = frappe.get_all(
        "Loyalty Member",
        filters={"loyalty_program": program, "company": ["!=", company]},
        fields=["name", "customer"],
        limit=0,
    )
    if not wrong:
        return
    names, customers = [row.name for row in wrong], [row.customer for row in wrong]
    frappe.db.sql("update `tabLoyalty Member` set company = %s where name in %s", (company, names))
    frappe.db.sql(
        "update `tabLoyalty Point Entry` set company = %s where loyalty_program = %s and customer in %s",
        (company, program, customers),
    )
    frappe.db.sql("update `tabLoyalty Message Log` set company = %s where member in %s", (company, names))
    if frappe.get_meta("Customer").has_field("rd_company"):
        frappe.db.sql("update `tabCustomer` set rd_company = %s where name in %s", (company, customers))
    print(f"  moved {len(names)} members to {company}")


# ---------------------------------------------------------------- members
def _members(rng, count, months, stores):
    existing = frappe.get_all("Loyalty Member", filters={"company": C.COMPANY}, pluck="name", order_by="creation asc")
    if len(existing) >= count:
        return existing

    used_names = set(frappe.get_all("Loyalty Member", pluck="member_name"))
    window = months * 30
    current_month = getdate(today()).month
    created = list(existing)
    for index in range(len(existing), count):
        gender = "Female" if rng.random() < 0.56 else "Male"
        for _attempt in range(50):
            name = f"{rng.choice(C.FEMALE_NAMES if gender == 'Female' else C.MALE_NAMES)} {rng.choice(C.SURNAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        store = rng.choices(stores, weights=C.STORE_WEIGHTS)[0]
        city = next(row[3] for row in C.STORES if row[0] == store)
        # Most members joined early in the window; a tail joined in the last month.
        joined_days_ago = int(window * rng.betavariate(2.2, 1.3)) if rng.random() < 0.85 else rng.randint(0, 28)
        birth_month = current_month if rng.random() < 0.12 else rng.randint(1, 12)
        doc = frappe.get_doc(
            {
                "doctype": "Loyalty Member",
                "member_name": name,
                "mobile_no": f"017005550{index:02d}" if index < 100 else f"01700556{index:03d}",
                "email": f"{name.lower().replace(' ', '.')}@example.com" if rng.random() < 0.72 else None,
                "gender": gender,
                "date_of_birth": f"{rng.randint(1975, 2004)}-{birth_month:02d}-{rng.randint(1, 28):02d}",
                "city": city,
                "home_store": store,
                "enrollment_date": add_days(today(), -joined_days_ago),
                "enrollment_channel": rng.choices(["POS", "Web", "Mobile App"], weights=[70, 18, 12])[0],
                "sms_opt_in": 1 if rng.random() < 0.93 else 0,
                "email_opt_in": 1 if rng.random() < 0.8 else 0,
            }
        )
        # Web and app sign-ups in the seed do not create CRM leads; the live demo shows that step.
        doc.flags.skip_crm_lead = True
        doc.insert(ignore_permissions=True)
        created.append(doc.name)
    return created


# ---------------------------------------------------------------- sales
def _sales(rng, member_names, months):
    from reckon_loyalty.api.pos import sync_transaction
    from reckon_loyalty.services.points import get_balance

    groups = list(C.ITEMS)
    plan = []
    for name in member_names:
        member = frappe.db.get_value(
            "Loyalty Member", name, ["name", "gender", "home_store", "enrollment_date", "qr_token"], as_dict=True
        )
        # A long-tailed number of visits: most members shop a few times, a few shop a lot.
        visits = min(24, int(rng.lognormvariate(1.2, 0.85)))
        days_as_member = max(0, date_diff(today(), member.enrollment_date))
        # One in five members stops coming: their visits all fall early, which feeds the lapsed segment.
        lapsed = rng.random() < 0.2 and days_as_member > 90
        # Category mix follows the order of C.ITEMS: Men, Women, Kids, Footwear, Accessories.
        weights = [46, 8, 14, 14, 18] if member.gender == "Male" else [12, 46, 16, 18, 8]
        for _visit in range(visits):
            days_ago = rng.randint(75 if lapsed else 0, days_as_member)
            lines = {}
            for _line in range(rng.choices([1, 2, 3, 4], weights=[38, 34, 18, 10])[0]):
                code, _item_name, _price = rng.choice(C.ITEMS[rng.choices(groups, weights=weights)[0]])
                lines[code] = lines.get(code, 0) + 1
            store = member.home_store if rng.random() < 0.8 else rng.choice([row[0] for row in C.STORES])
            plan.append((add_days(today(), -days_ago), member, store, lines, rng.random()))

    plan.sort(key=lambda row: str(row[0]))
    prices = {code: price for rows in C.ITEMS.values() for code, _name, price in rows}
    for number, (posting_date, member, store, lines, dice) in enumerate(plan, start=1):
        total = sum(prices[code] * qty for code, qty in lines.items())
        redeem = 0
        if dice < 0.14:
            balance = get_balance(
                frappe.db.get_value("Loyalty Member", member.name, "customer"), C.PROGRAM, C.COMPANY
            )
            redeem = min(balance, 600, int(total)) // 50 * 50
        sync_transaction(
            external_id=f"{SALE_PREFIX}{number:05d}",
            member=f"RL1:{member.qr_token}",
            store=store,
            terminal="TILL-01",
            posting_date=str(posting_date),
            posting_time=f"{rng.randint(11, 20):02d}:{rng.randint(0, 59):02d}:00",
            items=[{"item_code": code, "qty": qty} for code, qty in lines.items()],
            redeem_points=redeem,
        )
        if number % 20 == 0:
            frappe.db.commit()
            print(f"  sales posted: {number}/{len(plan)}")
    frappe.db.commit()


# ---------------------------------------------------------------- rewards, segments, campaigns
def _rewards(company, rng):
    for name, kind, points, value, discount, item, tier, description in C.REWARDS:
        if not frappe.db.exists("Loyalty Reward", name):
            frappe.get_doc(
                {
                    "doctype": "Loyalty Reward",
                    "reward_name": name,
                    "reward_type": kind,
                    "points_required": points,
                    "voucher_value": value,
                    "discount_percent": discount,
                    "item": item,
                    "minimum_tier": tier,
                    "description": description,
                    "company": company,
                    "valid_days": 30,
                }
            ).insert(ignore_permissions=True)
    if frappe.db.count("Loyalty Reward Redemption", {"company": company}):
        return
    from reckon_loyalty.services.members import refresh_member_stats

    for name in frappe.get_all("Loyalty Member", filters={"company": company}, pluck="name"):
        refresh_member_stats(name)
    rich = frappe.get_all(
        "Loyalty Member", filters={"company": company, "points_balance": [">=", 500]}, pluck="name",
        order_by="points_balance desc", limit=4,
    )
    for member in rich:
        frappe.get_doc(
            {"doctype": "Loyalty Reward Redemption", "member": member, "reward": "Tk 500 Shopping Voucher"}
        ).insert(ignore_permissions=True)
    frappe.db.commit()


def _segments(company):
    for spec in C.SEGMENTS:
        if not frappe.db.exists("Loyalty Segment", spec["segment_name"]):
            frappe.get_doc({"doctype": "Loyalty Segment", "company": company, **spec}).insert(ignore_permissions=True)


def _campaigns(company):
    from reckon_loyalty.services import campaigns as campaign_service

    for spec in C.CAMPAIGNS:
        spec = dict(spec)
        send, window = spec.pop("_send", False), spec.pop("_window", None)
        if frappe.db.exists("Loyalty Campaign", spec["campaign_name"]):
            continue
        doc = frappe.get_doc({"doctype": "Loyalty Campaign", "company": company, **spec})
        doc.insert(ignore_permissions=True)
        if send:
            campaign_service.dispatch(doc.name)
            if window:
                # Back-date the demo campaign so its offer window already holds sales to report.
                start, end = add_days(today(), window[0]), add_days(today(), window[1])
                sent_on = f"{start} 10:30:00"
                doc.db_set({"start_date": start, "end_date": end, "sent_on": sent_on})
                frappe.db.sql(
                    "update `tabLoyalty Message Log` set sent_on = %s where campaign = %s", (sent_on, doc.name)
                )
            campaign_service.refresh_results(doc.name)
    frappe.db.commit()
