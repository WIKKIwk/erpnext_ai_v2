frappe.provide("erpnext_ai.pages");

frappe.pages["ai-item-creator"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Item Creator"),
		single_column: true,
	});

	new erpnext_ai.pages.AIItemCreator(page);
};

erpnext_ai.pages.AIItemCreator = class AIItemCreator {
	constructor(page) {
		this.page = page;
		this.previewItems = [];

		this._buildLayout();
		this._bindActions();
	}

	_buildLayout() {
		this.$container = $(`
			<div class="ai-item-creator">
				<div class="text-muted mb-3">
					${__(
						'Bulk-create Items safely. First run <b>Preview</b>, then confirm creation. Enable <b>Allow AI Item Creation</b> in <b>AI Settings</b>.',
					)}
				</div>
				<div class="ai-item-form"></div>
				<div class="ai-item-preview mt-4"></div>
			</div>
		`).appendTo(this.page.body);

		this.fieldGroup = new frappe.ui.FieldGroup({
			body: this.$container.find(".ai-item-form"),
			fields: [
				{
					fieldtype: "Link",
					fieldname: "item_group",
					label: __("Item Group"),
					options: "Item Group",
					reqd: 1,
				},
				{
					fieldtype: "Link",
					fieldname: "stock_uom",
					label: __("Stock UOM"),
					options: "UOM",
					default: "Nos",
					reqd: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "create_disabled",
					label: __("Create as Disabled"),
					default: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "use_ai",
					label: __("Use AI to parse input"),
					default: 0,
					description: __("Uses the provider configured in AI Settings to interpret messy lists."),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Code",
					fieldname: "raw_text",
					label: __("Items (one per line)"),
					options: "Text",
					reqd: 1,
					description: __("Examples: \"CODE - Name\" or just \"Name\" per line."),
				},
			],
		});

		this.fieldGroup.make();
		this.$preview = this.$container.find(".ai-item-preview");
	}

	_bindActions() {
		this.page.set_primary_action(__("Preview"), () => this.preview());
		this.page.set_secondary_action(__("Create Items"), () => this.createItems());
	}

	_getValues() {
		const values = this.fieldGroup.get_values(true) || {};
		return {
			item_group: values.item_group,
			stock_uom: values.stock_uom,
			raw_text: values.raw_text || "",
			use_ai: values.use_ai ? 1 : 0,
			create_disabled: values.create_disabled ? 1 : 0,
		};
	}

	preview() {
		const values = this._getValues();
		if (!values.item_group || !values.stock_uom) {
			frappe.msgprint({
				title: __("Missing values"),
				message: __("Select Item Group and Stock UOM."),
				indicator: "orange",
			});
			return;
		}

		frappe.call({
			method: "erpnext_ai.api.preview_item_creation",
			args: {
				raw_text: values.raw_text,
				item_group: values.item_group,
				stock_uom: values.stock_uom,
				use_ai: values.use_ai,
			},
			freeze: true,
			freeze_message: __("Preparing preview..."),
			callback: (r) => {
				const data = r.message || {};
				this.previewItems = data.items || [];
				this.renderPreview(data);
			},
		});
	}

	renderPreview(data) {
		const warnings = data.warnings || [];
		const rows = data.items || [];

		if (!rows.length) {
			this.$preview.html(`<p class="text-muted">${__("No items to preview.")}</p>`);
			return;
		}

		const warningHtml = warnings.length
			? `<div class="alert alert-warning">${warnings.map((w) => frappe.utils.escape_html(w)).join("<br>")}</div>`
			: "";

		const bodyRows = rows
			.map((row) => {
				const issues = (row.issues || []).map((x) => frappe.utils.escape_html(x)).join("<br>");
				const status = row.exists ? __("Exists") : __("New");
				const statusClass = row.exists ? "badge badge-warning" : "badge badge-success";
				return `
					<tr>
						<td>${row.idx || ""}</td>
						<td><code>${frappe.utils.escape_html(row.item_code || "")}</code></td>
						<td>${frappe.utils.escape_html(row.item_name || "")}</td>
						<td>${frappe.utils.escape_html(row.item_group || "")}</td>
						<td>${frappe.utils.escape_html(row.stock_uom || "")}</td>
						<td><span class="${statusClass}">${status}</span></td>
						<td class="text-muted">${issues || ""}</td>
					</tr>
				`;
			})
			.join("");

		this.$preview.html(
			`
				${warningHtml}
				<div class="card">
					<div class="card-body">
						<div class="mb-2 text-muted">
							${__("Review the list. Items marked as <b>Exists</b> will be skipped on creation.")}
						</div>
						<div class="table-responsive">
							<table class="table table-bordered">
								<thead>
									<tr>
										<th style="width: 60px">#</th>
										<th>${__("Item Code")}</th>
										<th>${__("Item Name")}</th>
										<th>${__("Item Group")}</th>
										<th>${__("UOM")}</th>
										<th style="width: 90px">${__("Status")}</th>
										<th>${__("Issues")}</th>
									</tr>
								</thead>
								<tbody>${bodyRows}</tbody>
							</table>
						</div>
					</div>
				</div>
			`,
		);
	}

	createItems() {
		if (!this.previewItems || !this.previewItems.length) {
			frappe.msgprint({
				title: __("Nothing to create"),
				message: __("Run Preview first."),
				indicator: "orange",
			});
			return;
		}

		const values = this._getValues();
		const newCount = this.previewItems.filter((row) => !row.exists).length;

		frappe.confirm(
			__("Create {0} new Items? Existing Items will be skipped.", [newCount]),
			() => {
				frappe.call({
					method: "erpnext_ai.api.create_items_from_preview",
					args: {
						items: this.previewItems,
						create_disabled: values.create_disabled,
					},
					freeze: true,
					freeze_message: __("Creating Items..."),
					callback: (r) => {
						const data = r.message || {};
						const created = data.created || [];
						const skipped = data.skipped || [];
						const failed = data.failed || [];

						const lines = [];
						lines.push(__("Created: {0}", [created.length]));
						lines.push(__("Skipped: {0}", [skipped.length]));
						lines.push(__("Failed: {0}", [failed.length]));

						frappe.msgprint({
							title: __("Item creation complete"),
							message: lines.join("<br>"),
							indicator: failed.length ? "orange" : "green",
						});

						this.previewItems = [];
						this.$preview.empty();
					},
				});
			},
		);
	}
};

