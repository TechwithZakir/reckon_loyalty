frappe.ui.form.on("Loyalty Segment", {
	refresh(frm) {
		frm.fields_dict.preview_html.$wrapper.empty();
		frm.add_custom_button(__("Preview Members"), () => load_preview(frm)).addClass("btn-primary");
		if (frm.is_new()) return;

		load_preview(frm);
		frm.add_custom_button(__("Create Campaign"), () => {
			frappe.new_doc("Loyalty Campaign", { segment: frm.doc.name, company: frm.doc.company });
		});
		if (frappe.user.has_role(["Loyalty Manager", "System Manager"])) {
			frm.add_custom_button(__("Send to Frappe CRM"), () => {
				frappe.confirm(
					__("Create CRM Leads for the top 50 members of this segment so the team can follow up one by one?"),
					() => {
						frappe
							.call({
								method: "reckon_loyalty.services.crm_sync.push_segment",
								args: { segment: frm.doc.name },
								freeze: true,
							})
							.then((r) => {
								frappe.msgprint(
									__("{0} leads created, {1} skipped (already in CRM or could not be created).", [
										r.message.created,
										r.message.skipped,
									])
								);
							});
					}
				);
			});
		}
	},
});

function load_preview(frm) {
	const args = frm.is_dirty() || frm.is_new() ? { segment: JSON.stringify(frm.doc), save: 0 } : { segment: frm.doc.name };
	frappe.call({ method: "reckon_loyalty.services.segments.preview", args }).then((r) => {
		const { summary, members } = r.message;
		const esc = frappe.utils.escape_html;
		const money = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 0);
		const rows = members
			.map(
				(m) => `<tr>
					<td><a href="/app/loyalty-member/${encodeURIComponent(m.name)}">${esc(m.member_name)}</a></td>
					<td>${esc(m.mobile_no || "")}</td><td>${esc(m.tier || "")}</td><td>${esc(m.home_store || "")}</td>
					<td class="text-right">${money(m.lifetime_spend)}</td><td class="text-right">${m.total_orders}</td>
					<td class="text-right">${m.points_balance}</td>
					<td>${m.last_purchase_date ? frappe.datetime.str_to_user(m.last_purchase_date) : ""}</td>
				</tr>`
			)
			.join("");
		frm.fields_dict.preview_html.$wrapper.html(`
			<div class="rl-kpis rl-kpis-inline">
				<div class="rl-kpi"><span>${__("Members")}</span><b>${summary.members}</b></div>
				<div class="rl-kpi"><span>${__("Lifetime spend")}</span><b>${money(summary.spend)}</b></div>
				<div class="rl-kpi"><span>${__("Points held")}</span><b>${summary.points}</b></div>
				<div class="rl-kpi"><span>${__("Reachable by SMS")}</span><b>${summary.sms_reachable}</b></div>
				<div class="rl-kpi"><span>${__("Reachable by email")}</span><b>${summary.email_reachable}</b></div>
			</div>
			<table class="table table-bordered rl-table"><thead><tr>
				<th>${__("Member")}</th><th>${__("Mobile")}</th><th>${__("Tier")}</th><th>${__("Home store")}</th>
				<th class="text-right">${__("Lifetime spend")}</th><th class="text-right">${__("Orders")}</th>
				<th class="text-right">${__("Points")}</th><th>${__("Last purchase")}</th>
			</tr></thead><tbody>${rows || `<tr><td colspan="8" class="text-muted">${__("No members match these rules")}</td></tr>`}</tbody></table>
			${summary.members > members.length ? `<div class="text-muted small">${__("Showing the top {0} by lifetime spend", [members.length])}</div>` : ""}`);
	});
}
