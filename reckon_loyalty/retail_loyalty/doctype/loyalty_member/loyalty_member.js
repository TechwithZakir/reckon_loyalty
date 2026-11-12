frappe.ui.form.on("Loyalty Member", {
	refresh(frm) {
		frm.fields_dict.card_html.$wrapper.empty();
		frm.fields_dict.history_html.$wrapper.empty();
		if (frm.is_new()) return;

		frappe
			.call("reckon_loyalty.services.members.get_member_card", { member: frm.doc.name })
			.then((r) => r.message && render_member(frm, r.message));

		frm.add_custom_button(__("Open Digital Card"), () => {
			window.open(`/card/${frm.doc.qr_token}`, "_blank");
		});
		frm.add_custom_button(__("Refresh Statistics"), () => {
			frappe
				.call("reckon_loyalty.services.members.refresh_member", { member: frm.doc.name })
				.then(() => frm.reload_doc());
		});
		if (frappe.user.has_role(["Loyalty Manager", "System Manager"])) {
			frm.add_custom_button(
				__("Adjust Points"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "points",
								fieldtype: "Int",
								label: __("Points (+ credit, - debit)"),
								reqd: 1,
							},
							{ fieldname: "reason", fieldtype: "Data", label: __("Reason"), reqd: 1 },
						],
						(values) => {
							frappe
								.call("reckon_loyalty.services.members.adjust_points", {
									member: frm.doc.name,
									...values,
								})
								.then(() => frm.reload_doc());
						},
						__("Adjust Points")
					);
				},
				__("Actions")
			);
			frm.add_custom_button(
				__("Redeem a Reward"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "reward",
								fieldtype: "Link",
								options: "Loyalty Reward",
								label: __("Reward"),
								reqd: 1,
								get_query: () => ({ filters: { is_active: 1 } }),
							},
						],
						(values) => {
							frappe
								.call("reckon_loyalty.services.rewards.redeem_reward", {
									member: frm.doc.name,
									reward: values.reward,
								})
								.then((r) => {
									frappe.msgprint(
										__("Voucher {0} issued, valid till {1}.", [
											r.message.voucher_code.bold(),
											frappe.datetime.str_to_user(r.message.valid_till),
										])
									);
									frm.reload_doc();
								});
						},
						__("Redeem a Reward")
					);
				},
				__("Actions")
			);
			if (!frm.doc.crm_lead) {
				frm.add_custom_button(
					__("Create Frappe CRM Lead"),
					() => {
						frappe
							.call("reckon_loyalty.services.crm_sync.create_lead", { member: frm.doc.name })
							.then((r) => {
								if (r.message) frappe.show_alert({ message: __("CRM Lead {0} created", [r.message]), indicator: "green" });
								frm.reload_doc();
							});
					},
					__("Actions")
				);
			}
		}
	},
});

function money(value) {
	return format_currency(value || 0, frappe.defaults.get_default("currency"), 0);
}

function render_member(frm, data) {
	const p = data.profile;
	const esc = frappe.utils.escape_html;
	const next = p.next_tier
		? `${money(p.spend_to_next_tier)} ${__("more to reach")} <b>${esc(p.next_tier)}</b>`
		: __("Top tier reached");
	frm.fields_dict.card_html.$wrapper.html(`
		<div class="rl-member-head">
			<div class="rl-card" style="background:${esc(p.tier_color)}">
				<div class="rl-card-top"><span>${__("Member Card")}</span><span class="rl-chip">${esc(p.tier || "")}</span></div>
				<div class="rl-card-name">${esc(p.member_name)}</div>
				<div class="rl-card-no">${esc(p.card_number)}</div>
				<div class="rl-card-bottom"><span>${p.points_balance} ${__("pts")}</span><span>${money(p.points_value)}</span></div>
			</div>
			<div class="rl-qr-box">${p.qr_svg || ""}<div class="text-muted small">${__("Scan at the till")}</div></div>
			<div class="rl-facts">
				<div><span>${__("Points balance")}</span><b>${p.points_balance}</b></div>
				<div><span>${__("Worth")}</span><b>${money(p.points_value)}</b></div>
				<div><span>${__("Lifetime spend")}</span><b>${money(p.lifetime_spend)}</b></div>
				<div><span>${__("Orders")}</span><b>${p.total_orders}</b></div>
				<div class="rl-progress-row">
					<div class="rl-progress"><i style="width:${p.tier_progress}%"></i></div>
					<span class="small text-muted">${next}</span>
				</div>
			</div>
		</div>`);

	const invoices = (data.history || [])
		.map(
			(row) => `<tr>
				<td><a href="/app/sales-invoice/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td>
				<td>${frappe.datetime.str_to_user(row.posting_date)}</td>
				<td>${esc(row.loyalty_store || "")}</td>
				<td>${(row.items || []).map((i) => `${esc(i.item_name)} × ${i.qty}`).join("<br>")}</td>
				<td class="text-right">${money(row.grand_total)}</td>
				<td class="text-right">${row.is_return ? "" : "+" + (row.points_earned || 0)}</td>
				<td class="text-right">${row.points_redeemed ? "-" + row.points_redeemed : ""}</td>
			</tr>`
		)
		.join("");
	const ledger = (data.ledger || [])
		.map(
			(row) => `<tr>
				<td>${frappe.datetime.str_to_user(row.posting_date)}</td>
				<td>${esc(row.invoice || row.discretionary_reason || "")}</td>
				<td class="text-right ${row.loyalty_points < 0 ? "text-danger" : "text-success"}">${row.loyalty_points > 0 ? "+" : ""}${row.loyalty_points}</td>
				<td>${frappe.datetime.str_to_user(row.expiry_date)}</td>
			</tr>`
		)
		.join("");
	frm.fields_dict.history_html.$wrapper.html(`
		<h6 class="mt-2">${__("Recent purchases")}</h6>
		<table class="table table-bordered rl-table"><thead><tr>
			<th>${__("Invoice")}</th><th>${__("Date")}</th><th>${__("Store")}</th><th>${__("Items")}</th>
			<th class="text-right">${__("Total")}</th><th class="text-right">${__("Earned")}</th><th class="text-right">${__("Redeemed")}</th>
		</tr></thead><tbody>${invoices || `<tr><td colspan="7" class="text-muted">${__("No purchases yet")}</td></tr>`}</tbody></table>
		<h6 class="mt-4">${__("Points ledger")}</h6>
		<table class="table table-bordered rl-table"><thead><tr>
			<th>${__("Date")}</th><th>${__("Source")}</th><th class="text-right">${__("Points")}</th><th>${__("Expires")}</th>
		</tr></thead><tbody>${ledger || `<tr><td colspan="4" class="text-muted">${__("No points yet")}</td></tr>`}</tbody></table>`);
}
