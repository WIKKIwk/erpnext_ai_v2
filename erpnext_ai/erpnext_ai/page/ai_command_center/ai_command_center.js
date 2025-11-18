frappe.provide("erpnext_ai.pages");

frappe.pages["ai-command-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Command Center"),
		single_column: true,
	});

	const dashboard = new erpnext_ai.pages.AICommandCenter(page);

	page.set_primary_action(__("Generate Summary"), () => dashboard.generateSummary());
	page.set_secondary_action(__("Refresh Metrics"), () => dashboard.refreshContext());
};

erpnext_ai.pages.AICommandCenter = class AICommandCenter {
	constructor(page) {
		this.page = page;
		this.days = 30;
		this.context = null;

		this.$container = $(`
			<div class="ai-command-layout">
				<div class="ai-controls form-inline mb-4 gap-2">
					<label class="mr-2">${__("Period")}</label>
					<select class="form-control ai-period">
						<option value="7">7 ${__("days")}</option>
						<option value="30" selected>30 ${__("days")}</option>
						<option value="90">90 ${__("days")}</option>
					</select>
				</div>
				<div class="ai-context"></div>
				<div class="ai-output-section hide mt-4">
					<h5 class="mb-3">${__("Latest AI Summary")}</h5>
					<div class="ai-output card p-4"></div>
				</div>
			</div>
		`).appendTo(page.body);

		this.$period = this.$container.find(".ai-period");
		this.$context = this.$container.find(".ai-context");
		this.$outputSection = this.$container.find(".ai-output-section");
		this.$outputBody = this.$container.find(".ai-output");

		this.$period.on("change", () => {
			this.days = parseInt(this.$period.val(), 10) || 30;
			this.refreshContext();
		});

		this.refreshContext();
	}

	refreshContext() {
		frappe.call({
			method: "erpnext_ai.api.get_admin_context",
			args: { days: this.days },
			freeze: true,
			freeze_message: __("Collecting ERPNext metrics..."),
			callback: (r) => {
				this.context = r.message || {};
				this.renderContext();
			},
		});
	}

	renderContext() {
		if (!this.context || !this.context.meta) {
			this.$context.html(`<p class="text-muted">${__("No data available for this period.")}</p>`);
			return;
		}

		const metrics = this._buildMetrics(this.context.metrics || {});
		const topCustomers = (this.context.top_customers || []).map((row) => ({
			...row,
			amount_formatted: frappe.format(row.amount, { fieldtype: "Currency" }),
		}));

		this.$context.html(
			frappe.render_template("ai_dashboard", {
				meta: this.context.meta,
				metrics,
				top_customers: topCustomers,
			}),
		);
	}

	generateSummary() {
		frappe.call({
			method: "erpnext_ai.api.generate_admin_summary",
			args: {
				days: this.days,
			},
			freeze: true,
			freeze_message: __("Generating AI summary..."),
			callback: (r) => {
				const data = r.message || {};
				if (data.output) {
					const rendered = frappe.utils.markdown(data.output);
					this.$outputBody.html(rendered);
					this.$outputSection.removeClass("hide");
				}

				if (data.report_name) {
					frappe.show_alert({
						message: __("AI report {0} created", [data.report_name]),
						indicator: "green",
					});
				}

				this.refreshContext();
			},
			error: (err) => {
				frappe.msgprint({
					title: __("AI Summary Failed"),
					message: err.message || err.exc || __("Unable to generate summary."),
					indicator: "red",
				});
			},
		});
	}

	_buildMetrics(metrics) {
		const formatCount = (value) => frappe.format(value || 0, { fieldtype: "Int" });
		const formatAmount = (value) => frappe.format(value || 0, { fieldtype: "Currency" });

		const result = [];

		if (metrics.sales_invoices) {
			result.push({
				label: __("Sales Invoices"),
				primary: formatCount(metrics.sales_invoices.count),
				secondary: formatAmount(metrics.sales_invoices.amount),
			});
		}

		if (metrics.sales_orders) {
			result.push({
				label: __("Sales Orders"),
				primary: formatCount(metrics.sales_orders.count),
				secondary: formatAmount(metrics.sales_orders.amount),
			});
		}

		if (metrics.purchase_invoices) {
			result.push({
				label: __("Purchase Invoices"),
				primary: formatCount(metrics.purchase_invoices.count),
				secondary: formatAmount(metrics.purchase_invoices.amount),
			});
		}

		if (metrics.delivery_notes) {
			result.push({
				label: __("Delivery Notes"),
				primary: formatCount(metrics.delivery_notes.count),
				secondary: formatAmount(metrics.delivery_notes.amount),
			});
		}

		if (metrics.open_support_tickets !== undefined) {
			result.push({
				label: __("Open Support Tickets"),
				primary: formatCount(metrics.open_support_tickets),
				secondary: null,
			});
		}

		return result;
	}
};
