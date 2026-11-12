// Stands in for the retailer's POS during a demo. It talks to the same REST endpoints
// (reckon_loyalty.api.pos.*) that the real POS would call, and shows each request and response.
frappe.pages["loyalty-pos-simulator"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("POS Simulator"), single_column: true });
	const api = "reckon_loyalty.api.pos.";
	const esc = frappe.utils.escape_html;
	const currency = frappe.defaults.get_default("currency");
	const money = (v) => format_currency(v || 0, currency, 0);
	const state = { member: null, cart: [], items: [], redeem: 0, last: null };

	const store = page.add_field({ fieldname: "store", label: __("Store"), fieldtype: "Link", options: "Loyalty Store", reqd: 1 });
	const terminal = page.add_field({ fieldname: "terminal", label: __("Till"), fieldtype: "Data", default: "TILL-01" });
	page.add_inner_button(__("Dashboard"), () => frappe.set_route("loyalty-dashboard"));
	page.add_inner_button(__("Sync Log"), () => frappe.set_route("List", "Loyalty POS Sync Log"));

	const $body = $(`
		<div class="rl-pos">
			<div>
				<div class="rl-panel" style="margin-bottom:14px">
					<h5>${__("1. Identify the customer")}</h5>
					<div class="rl-sub">${__("Scan the QR code on the digital card, or type the card number or mobile number.")}</div>
					<div class="input-group">
						<input type="text" class="form-control rl-identifier" placeholder="${__("QR code, card number or mobile")}">
						<div class="input-group-append">
							<button class="btn btn-default rl-scan">${__("Scan QR")}</button>
							<button class="btn btn-primary rl-find">${__("Find")}</button>
							<button class="btn btn-default rl-new">${__("New member")}</button>
						</div>
					</div>
					<div class="rl-member mt-3"></div>
				</div>
				<div class="rl-panel">
					<h5>${__("2. Add items")}</h5>
					<input type="text" class="form-control rl-search mb-3" placeholder="${__("Search items")}">
					<div class="rl-pos-items"></div>
				</div>
			</div>
			<div>
				<div class="rl-panel" style="margin-bottom:14px">
					<h5>${__("3. Bill")}</h5>
					<div class="rl-cart-wrap"></div>
				</div>
				<div class="rl-panel">
					<h5>${__("API traffic")}</h5>
					<div class="rl-sub">${__("What the POS sends and what comes back")}</div>
					<div class="rl-json rl-traffic">${__("No call yet")}</div>
				</div>
			</div>
		</div>`).appendTo(page.main);

	function call(method, args, type) {
		const started = performance.now();
		return frappe
			.call({ method: api + method, args, type: type || "POST" })
			.then((r) => {
				show_traffic(method, args, r.message, Math.round(performance.now() - started));
				return r.message;
			});
	}

	function show_traffic(method, request, response, ms) {
		$body.find(".rl-traffic").text(
			`POST /api/method/${api}${method}   (${ms} ms)\n\n` +
				`${__("Request")}\n${JSON.stringify(request, null, 1)}\n\n${__("Response")}\n${JSON.stringify(response, null, 1)}`
		);
	}

	// ------------------------------------------------------------ member
	function find(identifier) {
		identifier = (identifier || $body.find(".rl-identifier").val() || "").trim();
		if (!identifier) return;
		call("lookup_member", { identifier }).then((member) => {
			state.member = member;
			state.redeem = 0;
			$body.find(".rl-identifier").val("");
			render_member();
			render_cart();
		});
	}

	function render_member() {
		const m = state.member;
		if (!m) return $body.find(".rl-member").html(`<div class="text-muted">${__("No customer selected")}</div>`);
		$body.find(".rl-member").html(`
			<div class="rl-member-head">
				<div class="rl-card" style="background:${esc(m.tier_color)};min-height:150px;width:280px">
					<div class="rl-card-top"><span>${esc(m.card_number)}</span><span class="rl-chip">${esc(m.tier || "")}</span></div>
					<div class="rl-card-name" style="margin-top:8px">${esc(m.member_name)}</div>
					<div class="rl-card-bottom"><span>${m.points_balance} ${__("pts")}</span><span>${money(m.points_value)}</span></div>
				</div>
				<div class="rl-facts">
					<div><span>${__("Mobile")}</span><b style="font-size:15px">${esc(m.mobile_no)}</b></div>
					<div><span>${__("Lifetime spend")}</span><b style="font-size:15px">${money(m.lifetime_spend)}</b></div>
					<div><span>${__("Earn rate")}</span><b style="font-size:13px">${esc(m.earn_rule || "")}</b></div>
					<div><span>${__("Next tier")}</span><b style="font-size:13px">${m.next_tier ? `${esc(m.next_tier)}: ${money(m.spend_to_next_tier)} ${__("to go")}` : __("Top tier")}</b></div>
				</div>
			</div>`);
	}

	function new_member() {
		const dialog = new frappe.ui.Dialog({
			title: __("Register a new member"),
			fields: [
				{ fieldname: "member_name", label: __("Full Name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "mobile_no", label: __("Mobile No"), fieldtype: "Data", reqd: 1, description: "01XXXXXXXXX" },
				{ fieldname: "email", label: __("Email"), fieldtype: "Data", options: "Email" },
				{ fieldtype: "Column Break" },
				{ fieldname: "gender", label: __("Gender"), fieldtype: "Select", options: "\nMale\nFemale\nOther" },
				{ fieldname: "date_of_birth", label: __("Date of Birth"), fieldtype: "Date" },
			],
			primary_action_label: __("Register"),
			primary_action(values) {
				call("register_member", Object.assign({ store: store.get_value() }, values)).then((member) => {
					dialog.hide();
					state.member = member;
					render_member();
					render_cart();
					frappe.show_alert({
						message: member.already_registered
							? __("This mobile is already a member: {0}", [member.card_number])
							: __("Card {0} issued. The card link was sent by SMS.", [member.card_number]),
						indicator: "green",
					});
				});
			},
		});
		dialog.show();
	}

	// ------------------------------------------------------------ items and cart
	function load_items(search) {
		frappe.call({ method: api + "get_items", args: { search, limit: 60 }, type: "GET" }).then((r) => {
			state.items = r.message || [];
			$body.find(".rl-pos-items").html(
				state.items
					.map(
						(item, index) => `<button class="rl-pos-item" data-index="${index}">
							<b>${esc(item.item_name)}</b><span>${esc(item.item_group)}</span><em>${money(item.rate)}</em></button>`
					)
					.join("") || `<div class="text-muted">${__("No items found")}</div>`
			);
		});
	}

	function totals() {
		const total = state.cart.reduce((sum, line) => sum + line.qty * line.rate, 0);
		const point_value = state.member ? state.member.point_value : 0;
		const max_redeem = state.member ? Math.min(state.member.points_balance, Math.floor(point_value ? total / point_value : 0)) : 0;
		state.redeem = Math.max(0, Math.min(state.redeem, max_redeem));
		return { total, max_redeem, discount: state.redeem * point_value, due: total - state.redeem * point_value };
	}

	function render_cart() {
		const t = totals();
		const rows = state.cart
			.map(
				(line, index) => `<tr>
					<td>${esc(line.item_name)}</td>
					<td><input type="number" min="1" class="form-control input-xs rl-qty" data-index="${index}" value="${line.qty}"></td>
					<td class="text-right">${money(line.rate)}</td><td class="text-right">${money(line.rate * line.qty)}</td>
					<td><button class="btn btn-xs btn-default rl-remove" data-index="${index}">×</button></td></tr>`
			)
			.join("");
		$body.find(".rl-cart-wrap").html(`
			<table class="table rl-table rl-cart"><thead><tr><th>${__("Item")}</th><th>${__("Qty")}</th><th class="text-right">${__("Rate")}</th><th class="text-right">${__("Amount")}</th><th></th></tr></thead>
			<tbody>${rows || `<tr><td colspan="5" class="text-muted">${__("The bill is empty")}</td></tr>`}</tbody></table>
			<div class="rl-totals">
				<span>${__("Total")}</span><span>${money(t.total)}</span>
				<span>${__("Redeem points")} <span class="text-muted">(${__("up to {0}", [t.max_redeem])})</span></span>
				<span><input type="number" min="0" max="${t.max_redeem}" class="form-control input-xs rl-redeem" style="width:90px;display:inline-block" value="${state.redeem}" ${t.max_redeem ? "" : "disabled"}>
					<button class="btn btn-xs btn-default rl-redeem-max" ${t.max_redeem ? "" : "disabled"}>${__("Max")}</button></span>
				<span>${__("Points discount")}</span><span>- ${money(t.discount)}</span>
				<span class="rl-due">${__("To pay")}</span><span class="rl-due">${money(t.due)}</span>
			</div>
			<button class="btn btn-primary btn-block rl-pay" ${state.cart.length && state.member ? "" : "disabled"}>${__("Complete sale")}</button>
			<div class="rl-result mt-3"></div>`);
		if (state.last) render_receipt();
	}

	function pay() {
		if (!store.get_value()) return frappe.msgprint(__("Choose the store first."));
		const t = totals();
		const payload = {
			external_id: `${(terminal.get_value() || "TILL").replace(/\s+/g, "")}-${Date.now()}`,
			member: state.member.qr_payload,
			store: store.get_value(),
			terminal: terminal.get_value(),
			items: state.cart.map((line) => ({ item_code: line.item_code, qty: line.qty, rate: line.rate })),
			redeem_points: state.redeem,
			payments: [{ mode_of_payment: "Cash", amount: t.due }],
		};
		$body.find(".rl-pay").prop("disabled", true);
		call("sync_transaction", payload)
			.then((result) => {
				state.last = result;
				state.cart = [];
				state.redeem = 0;
				return call("lookup_member", { identifier: payload.member }).then((member) => {
					state.member = member;
					show_traffic("sync_transaction", payload, result, 0);
					render_member();
					render_cart();
				});
			})
			.catch(() => $body.find(".rl-pay").prop("disabled", false));
	}

	function render_receipt() {
		const r = state.last;
		$body.find(".rl-result").html(`
			<div class="rl-receipt">
				<div class="rl-big">+${r.points_earned} ${__("points earned")}</div>
				<div>${__("Invoice")} <a href="/app/sales-invoice/${encodeURIComponent(r.invoice)}">${esc(r.invoice)}</a>: ${money(r.grand_total)}
					${r.points_redeemed ? `, ${__("{0} points redeemed ({1})", [r.points_redeemed, money(r.redeemed_amount)])}` : ""}</div>
				<div>${__("New balance")}: <b>${r.points_balance}</b> ${__("points")} (${money(r.points_value)}). ${__("Tier")}: <b>${esc(r.tier || "")}</b>
					${r.next_tier ? `. ${money(r.spend_to_next_tier)} ${__("more to reach")} ${esc(r.next_tier)}` : ""}</div>
			</div>`);
	}

	// ------------------------------------------------------------ events
	$body.on("click", ".rl-find", () => find());
	$body.on("keydown", ".rl-identifier", (e) => e.key === "Enter" && find());
	$body.on("click", ".rl-new", new_member);
	$body.on("click", ".rl-scan", () => {
		new frappe.ui.Scanner({
			dialog: true,
			multiple: false,
			on_scan(data) {
				find(data.decodedText);
			},
		});
	});
	$body.on("input", ".rl-search", frappe.utils.debounce((e) => load_items(e.target.value), 300));
	$body.on("click", ".rl-pos-item", (e) => {
		const item = state.items[$(e.currentTarget).data("index")];
		const line = state.cart.find((row) => row.item_code === item.item_code);
		if (line) line.qty += 1;
		else state.cart.push({ item_code: item.item_code, item_name: item.item_name, rate: item.rate, qty: 1 });
		state.last = null;
		render_cart();
	});
	$body.on("change", ".rl-qty", (e) => {
		state.cart[$(e.target).data("index")].qty = Math.max(1, parseInt(e.target.value, 10) || 1);
		render_cart();
	});
	$body.on("click", ".rl-remove", (e) => {
		state.cart.splice($(e.currentTarget).data("index"), 1);
		render_cart();
	});
	$body.on("change", ".rl-redeem", (e) => {
		state.redeem = parseInt(e.target.value, 10) || 0;
		render_cart();
	});
	$body.on("click", ".rl-redeem-max", () => {
		state.redeem = totals().max_redeem;
		render_cart();
	});
	$body.on("click", ".rl-pay", pay);

	frappe.call({ method: api + "get_stores", type: "GET" }).then((r) => {
		if (r.message && r.message.length && !store.get_value()) store.set_value(r.message[0].name);
	});
	render_member();
	render_cart();
	load_items();
};
