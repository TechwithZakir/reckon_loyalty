app_name = "reckon_loyalty"
app_title = "Retail Loyalty"
app_publisher = "Reckon Technologies Ltd."
app_description = "Retail CRM, membership and loyalty on ERPNext and Frappe CRM, with a POS integration API"
app_email = ""
app_license = "GPL-3.0-or-later"

# ERPNext owns customers, invoices and the points ledger. Frappe CRM is optional and is
# only touched through reckon_loyalty.services.crm_sync when it is installed.
required_apps = ["erpnext"]

add_to_apps_screen = [
    {
        "name": "reckon_loyalty",
        "logo": "/assets/reckon_loyalty/images/loyalty.svg",
        "title": "Retail Loyalty",
        "route": "/app/loyalty-dashboard",
        "has_permission": "reckon_loyalty.install.can_see_app",
    }
]

app_include_css = "/assets/reckon_loyalty/css/loyalty_desk.css"

before_install = "reckon_loyalty.install.create_roles"
after_install = "reckon_loyalty.install.after_install"
after_migrate = "reckon_loyalty.install.after_migrate"

# Both hooks return immediately unless the invoice's customer is a Loyalty Member, so
# other companies on a shared site are not affected.
doc_events = {
    "Sales Invoice": {
        "before_validate": "reckon_loyalty.services.members.stamp_invoice",
        "on_submit": "reckon_loyalty.services.members.on_invoice_change",
        "on_cancel": "reckon_loyalty.services.members.on_invoice_change",
    },
}

scheduler_events = {
    "cron": {
        "*/10 * * * *": ["reckon_loyalty.services.campaigns.send_due_campaigns"],
    },
    "daily": [
        "reckon_loyalty.services.members.refresh_all_members",
        "reckon_loyalty.services.members.award_birthday_bonus",
        "reckon_loyalty.services.segments.refresh_all_segments",
        "reckon_loyalty.services.rewards.expire_vouchers",
    ],
}

website_route_rules = [
    {"from_route": "/card/<token>", "to_route": "loyalty-card"},
]
