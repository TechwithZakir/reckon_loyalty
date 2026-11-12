frappe.pages["loyalty-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Loyalty Dashboard"), single_column: true });
	const $body = $('<div class="rl-dash"></div>').appendTo(page.main);

	const from = page.add_field({
		fieldname: "from_date",
		label: __("From"),
		fieldtype: "Date",
		default: frappe.datetime.add_days(frappe.datetime.get_today(), -89),
		change: () => load(),
	});
	const to = page.add_field({
		fieldname: "to_date",
		label: __("To"),
		fieldtype: "Date",
		default: frappe.datetime.get_today(),
		change: () => load(),
	});
	const store = page.add_field({
		fieldname: "store",
		label: __("Store"),
		fieldtype: "Link",
		options: "Loyalty Store",
		change: () => load(),
	});
	page.set_primary_action(__("Refresh"), () => load(), "refresh");
	page.add_inner_button(__("POS Simulator"), () => frappe.set_route("loyalty-pos-simulator"));
	page.add_inner_button(__("Members"), () => frappe.set_route("List", "Loyalty Member"));
	page.add_inner_button(__("Campaigns"), () => frappe.set_route("List", "Loyalty Campaign"));

	let timer = null;
	function load() {
		clearTimeout(timer);
		timer = setTimeout(() => {
			frappe
				.call("reckon_loyalty.services.dashboard.get_data", {
					from_date: from.get_value(),
					to_date: to.get_value(),
					store: store.get_value(),
				})
				.then((r) => render(r.message));
		}, 150);
	}

	const esc = frappe.utils.escape_html;
	const num = (v) => (v || 0).toLocaleString("en-IN");
	let currency = null;
	const money = (v) => format_currency(v || 0, currency, 0);

	function kpi(label, value, note) {
		return `<div class="rl-kpi"><span>${label}</span><b>${value}</b>${note ? `<small>${note}</small>` : ""}</div>`;
	}

	function render(d) {
		currency = d.currency;
		const k = d.kpis;
		page.set_title(d.brand ? `${d.brand}: ${__("Loyalty Dashboard")}` : __("Loyalty Dashboard"));
		const max_store = Math.max(1, ...d.stores.map((s) => s.revenue));

		$body.html(`
			${d.demo_mode ? `<div class="rl-banner">${__("Demo mode is on: campaign SMS and email are logged, not sent.")}</div>` : ""}
			<div class="rl-kpis">
				${kpi(__("Members"), num(k.members), __("{0} joined in period", [num(k.new_members)]))}
				${kpi(__("Active members"), num(k.active_members), __("{0}% of members bought in period", [k.active_rate]))}
				${kpi(__("Member sales"), money(k.revenue), __("{0} orders", [num(k.orders)]))}
				${kpi(__("Average basket"), money(k.avg_basket), __("{0}% of buyers came back", [k.repeat_rate]))}
				${kpi(__("Points issued"), num(k.points_issued), __("{0} redeemed ({1}%)", [num(k.points_redeemed), k.redemption_rate]))}
				${kpi(__("Points outstanding"), num(k.outstanding_points), __("Liability {0}", [money(k.points_liability)]))}
				${kpi(__("Expiring in 30 days"), num(k.expiring_points), __("points"))}
				${kpi(__("POS transactions synced"), num(d.pos_sync.success), __("{0} failed, average {1} ms", [d.pos_sync.failed, d.pos_sync.avg_ms]))}
			</div>
			<div class="rl-grid">
				<div class="rl-panel rl-two-third"><h5>${__("Member sales by month")}</h5><div class="rl-sub">${__("Last six months")}</div><div id="rl-chart-sales"></div></div>
				<div class="rl-panel rl-third"><h5>${__("Members by tier")}</h5><div class="rl-sub">${__("All members")}</div><div id="rl-chart-tier"></div></div>
				<div class="rl-panel"><h5>${__("New members by month")}</h5><div class="rl-sub">${__("Last six months")}</div><div id="rl-chart-enrol"></div></div>
				<div class="rl-panel"><h5>${__("Sales by category")}</h5><div class="rl-sub">${__("Selected period")}</div><div id="rl-chart-cat"></div></div>
				<div class="rl-panel"><h5>${__("Sales by store")}</h5><div class="rl-sub">${__("Selected period")}</div>
					<table class="table rl-table"><thead><tr><th>${__("Store")}</th><th class="text-right">${__("Sales")}</th><th></th><th class="text-right">${__("Orders")}</th><th class="text-right">${__("Members")}</th></tr></thead><tbody>
					${d.stores.map((s) => `<tr><td>${esc(s.store)}</td><td class="text-right">${money(s.revenue)}</td><td style="width:22%"><div class="rl-bar"><i style="width:${Math.round((s.revenue / max_store) * 100)}%"></i></div></td><td class="text-right">${num(s.orders)}</td><td class="text-right">${num(s.members)}</td></tr>`).join("") || empty(5)}
					</tbody></table></div>
				<div class="rl-panel"><h5>${__("Behaviour segments")}</h5><div class="rl-sub">${__("Recency and frequency of every member")}</div><div id="rl-chart-rfm"></div></div>
				<div class="rl-panel"><h5>${__("Top members")}</h5><div class="rl-sub">${__("By spend in the selected period")}</div>
					<table class="table rl-table"><thead><tr><th>${__("Member")}</th><th>${__("Tier")}</th><th class="text-right">${__("Spend")}</th><th class="text-right">${__("Orders")}</th><th class="text-right">${__("Points")}</th></tr></thead><tbody>
					${d.top_members.map((m) => `<tr><td><a href="/app/loyalty-member/${encodeURIComponent(m.name)}">${esc(m.member_name)}</a></td><td>${esc(m.tier || "")}</td><td class="text-right">${money(m.revenue)}</td><td class="text-right">${num(m.orders)}</td><td class="text-right">${num(m.points_balance)}</td></tr>`).join("") || empty(5)}
					</tbody></table></div>
				<div class="rl-panel"><h5>${__("Saved segments")}</h5><div class="rl-sub">${__("Refreshed nightly and on preview")}</div>
					<table class="table rl-table"><thead><tr><th>${__("Segment")}</th><th class="text-right">${__("Members")}</th><th class="text-right">${__("Lifetime spend")}</th></tr></thead><tbody>
					${d.segments.map((s) => `<tr><td><a href="/app/loyalty-segment/${encodeURIComponent(s.name)}">${esc(s.name)}</a></td><td class="text-right">${num(s.member_count)}</td><td class="text-right">${money(s.total_spend)}</td></tr>`).join("") || empty(3)}
					</tbody></table></div>
				<div class="rl-panel rl-wide"><h5>${__("Campaigns")}</h5><div class="rl-sub">${__("Reach and sales by targeted members inside the offer window")}</div>
					<table class="table rl-table"><thead><tr><th>${__("Campaign")}</th><th>${__("Segment")}</th><th>${__("Channel")}</th><th>${__("Status")}</th><th class="text-right">${__("Targeted")}</th><th class="text-right">${__("SMS")}</th><th class="text-right">${__("Email")}</th><th class="text-right">${__("Orders")}</th><th class="text-right">${__("Revenue")}</th></tr></thead><tbody>
					${d.campaigns.map((c) => `<tr><td><a href="/app/loyalty-campaign/${encodeURIComponent(c.name)}">${esc(c.name)}</a></td><td>${esc(c.segment || "")}</td><td>${esc(c.channel)}</td><td>${esc(c.status)}</td><td class="text-right">${num(c.targeted)}</td><td class="text-right">${num(c.sms_sent)}</td><td class="text-right">${num(c.email_sent)}</td><td class="text-right">${num(c.attributed_orders)}</td><td class="text-right">${money(c.attributed_revenue)}</td></tr>`).join("") || empty(9)}
					</tbody></table></div>
			</div>`);

		const months = d.trend.map((t) => moment(t.month + "-01").format("MMM YY"));
		chart("#rl-chart-sales", {
			type: "bar",
			data: { labels: months, datasets: [{ name: __("Member sales"), values: d.trend.map((t) => Math.round(t.revenue)) }] },
			colors: ["#2563eb"],
			tooltipOptions: { formatTooltipY: (v) => money(v) },
		});
		chart("#rl-chart-enrol", {
			type: "line",
			data: { labels: months, datasets: [{ name: __("New members"), values: d.trend.map((t) => t.new_members) }] },
			colors: ["#0d9488"],
			lineOptions: { regionFill: 1 },
		});
		if (d.tiers.some((t) => t.members)) {
			chart("#rl-chart-tier", {
				type: "donut",
				data: { labels: d.tiers.map((t) => t.tier), datasets: [{ values: d.tiers.map((t) => t.members) }] },
				colors: d.tiers.map((t) => t.color),
				height: 250,
			});
		}
		if (d.categories.length) {
			chart("#rl-chart-cat", {
				type: "bar",
				data: { labels: d.categories.map((c) => c.category), datasets: [{ name: __("Sales"), values: d.categories.map((c) => Math.round(c.revenue)) }] },
				colors: ["#7c3aed"],
				tooltipOptions: { formatTooltipY: (v) => money(v) },
			});
		}
		if (d.behaviour.length) {
			chart("#rl-chart-rfm", {
				type: "bar",
				data: { labels: d.behaviour.map((b) => b.segment), datasets: [{ name: __("Members"), values: d.behaviour.map((b) => b.members) }] },
				colors: ["#ea580c"],
			});
		}
	}

	function empty(cols) {
		return `<tr><td colspan="${cols}" class="text-muted">${__("Nothing in this period")}</td></tr>`;
	}

	function chart(selector, options) {
		const el = $body.find(selector)[0];
		if (!el) return;
		new frappe.Chart(el, Object.assign({ height: 240, axisOptions: { xAxisMode: "tick", shortenYAxisNumbers: 1 }, barOptions: { spaceRatio: 0.45 } }, options));
	}

	load();
};
