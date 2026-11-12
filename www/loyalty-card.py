import frappe

from reckon_loyalty.api.member import card_data

no_cache = 1


def get_context(context):
    token = frappe.form_dict.get("token")
    context.no_cache = 1
    context.data = card_data(token) if token else None
    context.token = token
    if not context.data:
        frappe.local.response["http_status_code"] = 404
    return context
