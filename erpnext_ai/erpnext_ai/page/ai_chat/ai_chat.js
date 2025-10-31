frappe.provide("erpnext_ai.pages");

frappe.pages["ai-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Assistant"),
		single_column: true,
	});

	const chat = new erpnext_ai.pages.AIChat(page);

	page.set_primary_action(__("Send"), () => chat.sendMessage(), "send");
	page.set_secondary_action(__("New Chat"), () => chat.startNewConversation(true), "plus");
};

erpnext_ai.pages.AIChat = class AIChat {
	constructor(page) {
		this.page = page;
		this.conversation = null;
		this.days = 30;
		this.includeContext = true;
		this.isSending = false;
		this.$typingIndicator = null;
		this.$pendingUserEcho = null;

		this._buildLayout();
		this.startNewConversation();
	}

	_buildLayout() {
		const styles = `
			:root {
				--ai-chat-app-bg: #ececf1;
				--ai-chat-feed-bg: #f7f7f8;
				--ai-chat-panel: rgba(255, 255, 255, 0.75);
				--ai-chat-border: #d0d7de;
				--ai-chat-text: #1f2937;
				--ai-chat-muted: #6b7280;
				--ai-chat-assistant-bg: #f7f7f8;
				--ai-chat-user-bg: #e5e7eb;
				--ai-chat-user-text: #111827;
				--ai-chat-shadow: 0 18px 40px -24px rgba(15, 23, 42, 0.35);
				--ai-chat-input-bg: #ffffff;
				--ai-chat-input-border: #d0d7de;
				--ai-chat-accent: #1f272f;
				--ai-chat-accent-hover: #13171d;
				--ai-chat-button-text: #f8fafc;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) {
				--ai-chat-app-bg: #343541;
				--ai-chat-feed-bg: #343541;
				--ai-chat-panel: rgba(64, 65, 79, 0.8);
				--ai-chat-border: #565869;
				--ai-chat-text: #ececf1;
				--ai-chat-muted: #a1a6b4;
				--ai-chat-assistant-bg: #444654;
				--ai-chat-user-bg: #343541;
				--ai-chat-user-text: #f8fafc;
				--ai-chat-shadow: 0 -12px 32px rgba(0, 0, 0, 0.45);
				--ai-chat-input-bg: #40414f;
				--ai-chat-input-border: #565869;
				--ai-chat-accent: #d1d5db;
				--ai-chat-accent-hover: #e5e7eb;
				--ai-chat-button-text: #111827;
			}

			body[data-route="ai-chat"],
			body[data-page-route="ai-chat"] {
				background: var(--ai-chat-app-bg);
			}

			.ai-chat-container {
				max-width: 1024px;
				margin: 0 auto;
				padding: 2rem 1.25rem 3rem;
				min-height: calc(100vh - 100px);
				display: flex;
				flex-direction: column;
				gap: 2rem;
				background: var(--ai-chat-app-bg);
			}

			.ai-chat-container.chat-active {
				height: calc(100vh - 100px);
				max-height: calc(100vh - 100px);
				overflow: hidden;
			}

			.ai-chat-hero {
				position: relative;
				overflow: hidden;
				border-radius: 18px;
				padding: 2.5rem clamp(2rem, 3vw, 3rem);
				background: linear-gradient(145deg, rgba(58, 61, 66, 0.16), rgba(58, 61, 66, 0));
				border: 1px solid var(--ai-chat-border);
				box-shadow: var(--ai-chat-shadow);
				text-align: center;
				color: var(--ai-chat-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-hero {
				background: linear-gradient(145deg, rgba(58, 61, 66, 0.28), rgba(58, 61, 66, 0));
			}

			.ai-chat-hero-icon {
				width: 64px;
				height: 64px;
				margin: 0 auto 1.5rem;
				border-radius: 22px;
				background: rgba(58, 61, 66, 0.16);
				display: flex;
				align-items: center;
				justify-content: center;
				font-weight: 700;
				font-size: 1.35rem;
				letter-spacing: -0.04em;
				color: var(--ai-chat-accent);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-hero-icon {
				background: rgba(58, 61, 66, 0.22);
			}

			.ai-chat-hero h2 {
				font-size: clamp(1.75rem, 3vw, 2.15rem);
				font-weight: 600;
				margin-bottom: 0.85rem;
			}

			.ai-chat-hero p {
				max-width: 680px;
				margin: 0 auto 2.25rem;
				color: var(--ai-chat-muted);
				font-size: 1rem;
				line-height: 1.7;
			}

			.ai-chat-hero-suggestions {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
				gap: 1rem;
				margin-bottom: 2.25rem;
			}

			.hero-suggestion {
				display: block;
				width: 100%;
				text-align: left;
				padding: 1.25rem 1.4rem;
				border-radius: 14px;
				border: 1px solid var(--ai-chat-border);
				background: rgba(255, 255, 255, 0.85);
				color: var(--ai-chat-text);
				cursor: pointer;
				transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .hero-suggestion {
				background: rgba(64, 65, 79, 0.75);
				border-color: #4a4c6a;
				color: var(--ai-chat-text);
			}

			.hero-suggestion strong {
				display: block;
				font-size: 1rem;
				font-weight: 600;
				margin-bottom: 0.6rem;
			}

			.hero-suggestion span {
				display: block;
				font-size: 0.9rem;
				color: var(--ai-chat-muted);
				line-height: 1.5;
			}

			.hero-suggestion:hover {
				transform: translateY(-2px);
				border-color: var(--ai-chat-accent);
				background: rgba(255, 255, 255, 0.95);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .hero-suggestion:hover {
				background: rgba(64, 65, 79, 0.85);
				border-color: rgba(58, 61, 66, 0.5);
			}

			.hero-actions {
				display: flex;
				gap: 1rem;
				justify-content: center;
				flex-wrap: wrap;
			}

			.hero-actions .btn {
				border-radius: 999px;
				padding: 0.75rem 1.75rem;
			}

			.hero-actions .btn-primary {
				background: var(--ai-chat-accent);
				border-color: var(--ai-chat-accent);
				color: var(--ai-chat-button-text);
				box-shadow: 0 6px 18px rgba(50, 52, 58, 0.35);
			}

			.hero-actions .btn-primary:hover,
			.ai-chat-buttons .btn-primary:hover {
				background: var(--ai-chat-accent-hover);
				border-color: var(--ai-chat-accent-hover);
			}

			.hero-actions .btn-default {
				border: 1px solid var(--ai-chat-border);
				background: transparent;
				color: var(--ai-chat-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .hero-actions .btn-default {
				border-color: #4a4c6a;
				color: var(--ai-chat-text);
				background: rgba(15, 16, 25, 0.35);
			}

			.ai-chat-hero.hidden {
				display: none;
			}

			.ai-chat-wrapper {
				flex: 1;
				min-height: 0;
				display: flex;
				flex-direction: column;
				background: var(--ai-chat-feed-bg);
				border-radius: 20px;
				border: 1px solid var(--ai-chat-border);
				overflow: hidden;
				position: relative;
			}

			.ai-chat-container.chat-active .ai-chat-wrapper {
				height: 100%;
				display: grid;
				grid-template-rows: 1fr auto;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-wrapper {
				border-color: #4a4c6a;
			}

			.ai-chat-feed {
				flex: 1;
				overflow-y: auto;
				padding: 1.5rem 0 2rem;
				display: flex;
				flex-direction: column;
				background: var(--ai-chat-feed-bg);
				scrollbar-width: thin;
				scrollbar-color: rgba(148, 163, 184, 0.4) transparent;
			}

			.ai-chat-container.chat-active .ai-chat-feed {
				padding: 1.5rem 0 1.5rem;
			}

			.ai-chat-feed::-webkit-scrollbar {
				width: 6px;
			}

			.ai-chat-feed::-webkit-scrollbar-thumb {
				background: rgba(148, 163, 184, 0.4);
				border-radius: 999px;
			}

			.ai-chat-feed::after {
				content: "";
				height: 1rem;
				flex-shrink: 0;
			}

			.ai-chat-message {
				padding: 0 1.75rem;
			}

			.ai-chat-row {
				display: flex;
				align-items: flex-start;
				gap: 1.25rem;
				padding: 1.25rem 0;
				border-bottom: 1px solid rgba(148, 163, 184, 0.2);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-row {
				border-color: rgba(86, 88, 105, 0.45);
			}

			.ai-chat-row:last-child {
				border-bottom: none;
			}

			.ai-chat-row.system {
				justify-content: center;
			}

			.ai-chat-avatar {
				width: 42px;
				height: 42px;
				border-radius: 999px;
				display: flex;
				align-items: center;
				justify-content: center;
				font-weight: 600;
				font-size: 0.85rem;
				color: #ffffff;
				flex-shrink: 0;
				box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08);
				background: linear-gradient(135deg, #202123, #2c2d3d);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-avatar {
				box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
			}

			.ai-chat-avatar.assistant {
				background: linear-gradient(140deg, #2f3135, #3d4047, #3a3d42);
				box-shadow: 0 8px 20px rgba(50, 52, 58, 0.35);
			}

			.ai-chat-avatar.user {
				background: linear-gradient(145deg, #202123, #2f3341);
			}

			.ai-chat-avatar-initial {
				display: block;
				font-weight: 600;
				letter-spacing: -0.03em;
			}

			.ai-chat-content {
				flex: 1;
				max-width: 100%;
			}

			.ai-chat-content.system {
				text-align: center;
			}

			.ai-chat-bubble {
				padding: 1.1rem 1.25rem;
				border-radius: 16px;
				font-size: 0.97rem;
				line-height: 1.65;
				max-width: 100%;
				word-wrap: anywhere;
				background: rgba(255, 255, 255, 0.6);
				color: var(--ai-chat-text);
				box-shadow: none;
				border: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble {
				background: rgba(64, 65, 79, 0.65);
			}

			.ai-chat-bubble.assistant {
				background: var(--ai-chat-assistant-bg);
				color: var(--ai-chat-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble.assistant {
				background: #444654;
			}

			.ai-chat-bubble.user {
				background: var(--ai-chat-user-bg);
				color: var(--ai-chat-user-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble.user {
				background: #343541;
				color: var(--ai-chat-text);
				box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
			}

			.ai-chat-bubble.system {
				background: transparent;
				color: var(--ai-chat-muted);
				padding: 0.75rem 0;
			}

			.ai-chat-bubble.pending {
				display: inline-flex;
				align-items: center;
				gap: 0.9rem;
				color: var(--ai-chat-muted);
				background: transparent;
				padding-left: 0;
			}

			.ai-chat-bubble.pending .typing-dots {
				display: inline-flex;
				gap: 0.4rem;
			}

			.ai-chat-bubble.pending .typing-dots span {
				width: 0.5rem;
				height: 0.5rem;
				border-radius: 50%;
				background: var(--ai-chat-muted);
				animation: ai-chat-pulse 1.4s infinite ease-in-out;
			}

			.ai-chat-bubble.pending .typing-dots span:nth-child(2) {
				animation-delay: 0.2s;
			}

			.ai-chat-bubble.pending .typing-dots span:nth-child(3) {
				animation-delay: 0.4s;
			}

			.ai-chat-bubble.error {
				background: #fef2f2;
				border: 1px solid #fecaca;
				color: #dc2626;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble.error {
				background: #7f1d1d;
				border-color: #991b1b;
				color: #fca5a5;
			}

			@keyframes ai-chat-pulse {
				0%, 80%, 100% {
					transform: scale(0.8);
					opacity: 0.45;
				}
				40% {
					transform: scale(1);
					opacity: 1;
				}
			}

			.ai-chat-meta {
				font-size: 0.75rem;
				color: var(--ai-chat-muted);
				margin-top: 0.75rem;
			}

			.ai-chat-context {
				margin-top: 0.75rem;
				text-align: left;
			}

			.ai-chat-context summary {
				cursor: pointer;
				color: var(--ai-chat-accent);
				font-size: 0.85rem;
			}

			.ai-chat-context pre {
				margin-top: 0.5rem;
				padding: 1rem;
				border-radius: 12px;
				background: rgba(15, 23, 42, 0.04);
				color: var(--ai-chat-text);
				overflow-x: auto;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-context pre {
				background: rgba(255, 255, 255, 0.05);
				color: #f8fafc;
			}

			.ai-chat-input {
				padding: 1.75rem clamp(1.5rem, 3vw, 2rem) 2rem;
				border-top: 1px solid var(--ai-chat-border);
				background: var(--ai-chat-feed-bg);
				display: flex;
				flex-direction: column;
				gap: 1rem;
				position: sticky;
				bottom: 0;
				left: 0;
				right: 0;
				z-index: 5;
				backdrop-filter: blur(8px);
				-webkit-backdrop-filter: blur(8px);
			}

			.ai-chat-container.chat-active .ai-chat-input {
				padding: 1.25rem clamp(1.5rem, 3vw, 2rem) 1.5rem;
			}

			.ai-chat-input-shell {
				background: var(--ai-chat-input-bg);
				border: 1px solid var(--ai-chat-input-border);
				border-radius: 20px;
				padding: 1rem 1.5rem;
				display: flex;
				flex-direction: column;
				gap: 1.25rem;
				box-shadow: var(--ai-chat-shadow);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-input-shell {
				box-shadow: 0 -18px 32px rgba(0, 0, 0, 0.45);
			}

			.ai-chat-input textarea {
				width: 100%;
				min-height: 72px;
				resize: vertical;
				border-radius: 0;
				padding: 0;
				font-size: 1rem;
				background: transparent;
				border: none;
				color: var(--ai-chat-text);
				font-family: inherit;
			}

			.ai-chat-input textarea:focus {
				outline: none;
				box-shadow: none;
			}

			.ai-chat-actions {
				display: flex;
				justify-content: space-between;
				align-items: center;
				flex-wrap: wrap;
				gap: 1rem;
			}

			.ai-chat-controls {
				display: flex;
				align-items: center;
				gap: 1rem;
				flex-wrap: wrap;
				font-size: 0.85rem;
				color: var(--ai-chat-muted);
			}

			.ai-chat-controls label {
				display: inline-flex;
				align-items: center;
				gap: 0.5rem;
				margin: 0;
			}

			.ai-chat-controls input[type="checkbox"] {
				width: 16px;
				height: 16px;
			}

			.ai-chat-controls select {
				background: transparent;
				border-radius: 999px;
				border: 1px solid var(--ai-chat-border);
				padding: 0.3rem 1.25rem 0.3rem 0.75rem;
				font-size: 0.85rem;
				color: var(--ai-chat-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-controls select {
				border-color: #4a4c6a;
				color: var(--ai-chat-text);
				background: rgba(64, 65, 79, 0.65);
			}

			.ai-chat-buttons {
				display: flex;
				gap: 0.6rem;
				align-items: center;
				flex-wrap: wrap;
			}

			.ai-chat-buttons .btn {
				border-radius: 999px;
				font-weight: 500;
				padding: 0.6rem 1.4rem;
			}

			.ai-chat-buttons .btn-default {
				background: transparent;
				border: 1px solid var(--ai-chat-border);
				color: var(--ai-chat-text);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-buttons .btn-default {
				border-color: #4a4c6a;
				color: var(--ai-chat-text);
				background: rgba(15, 16, 25, 0.35);
			}

			.ai-chat-buttons .btn-default:hover {
				border-color: rgba(58, 61, 66, 0.5);
				color: var(--ai-chat-accent);
			}

			.ai-chat-buttons .btn-primary {
				background: var(--ai-chat-accent);
				border-color: var(--ai-chat-accent);
				color: var(--ai-chat-button-text);
				box-shadow: 0 6px 18px rgba(58, 61, 66, 0.28);
			}

			.ai-chat-input-footer {
				text-align: center;
				font-size: 0.76rem;
				color: var(--ai-chat-muted);
			}

			@media (max-width: 768px) {
				.ai-chat-container {
					padding: 1.5rem 1rem 2.5rem;
				}

				.ai-chat-container.chat-active {
					height: calc(100vh - 80px);
					max-height: calc(100vh - 80px);
				}

				.ai-chat-hero {
					padding: 1.75rem 1.25rem;
					text-align: left;
				}

				.ai-chat-hero-icon {
					margin-bottom: 1rem;
					width: 52px;
					height: 52px;
					font-size: 1.1rem;
				}

				.ai-chat-hero h2 {
					font-size: 1.6rem;
				}

				.ai-chat-hero p {
					margin-bottom: 1.5rem;
				}

				.ai-chat-hero-suggestions {
					grid-template-columns: 1fr;
				}

				.hero-actions {
					align-items: stretch;
				}

				.hero-actions .btn {
					width: 100%;
					justify-content: center;
				}

				.ai-chat-row {
					flex-direction: column;
				}

				.ai-chat-avatar {
					width: 36px;
					height: 36px;
				}

				.ai-chat-row.system {
					align-items: center;
				}

				.ai-chat-actions {
					flex-direction: column;
					align-items: stretch;
				}

				.ai-chat-buttons {
					width: 100%;
					justify-content: flex-start;
				}

				.ai-chat-buttons .btn {
					width: 100%;
					justify-content: center;
				}

				.ai-chat-feed {
					padding: 1.25rem 0 1.25rem;
				}

				.ai-chat-input-shell {
					padding: 0.85rem 1rem;
					gap: 1rem;
				}
			}
		`;

		if (!document.getElementById("ai-chat-styles")) {
			$("<style>").attr("id", "ai-chat-styles").text(styles).appendTo("head");
		}

		const suggestionCards = [
			{
				message: __("Give me a quick revenue summary for the last quarter."),
				title: __("Spot revenue trends"),
				description: __("See how revenue moved and which products led the change."),
			},
			{
				message: __("Highlight overdue receivables and the customers behind them."),
				title: __("Track overdue invoices"),
				description: __("Stay ahead of pending payments before they become a risk."),
			},
			{
				message: __("Which products drove the highest gross margin this month?"),
				title: __("Find top performers"),
				description: __("See which products and teams delivered the best results."),
			},
		];

		const suggestionsHtml = suggestionCards
			.map((card) => {
				const message = frappe.utils.escape_html(card.message);
				const title = frappe.utils.escape_html(card.title);
				const description = frappe.utils.escape_html(card.description);

				return `
					<button type="button" class="hero-suggestion" data-message="${message}">
						<strong>${title}</strong>
						<span>${description}</span>
					</button>
				`;
			})
			.join("");

		this.$page = $('<div class="ai-chat-container"></div>').appendTo(this.page.body);

		this.$hero = $(`
			<div class="ai-chat-hero">
				<div class="ai-chat-hero-icon" aria-hidden="true">AI</div>
				<h2>${__("Ask ERPNext like ChatGPT")}</h2>
				<p>${__("Converse in natural language and let the assistant generate insights, summaries, and follow-up actions instantly.")}</p>
				<div class="ai-chat-hero-suggestions">
					${suggestionsHtml}
				</div>
				<div class="hero-actions">
					<button class="btn btn-primary btn-lg btn-hero-summary">
						${__("Generate Business Summary")}
					</button>
					<button class="btn btn-default btn-lg btn-hero-start">
						${__("Start Conversation")}
					</button>
				</div>
			</div>
		`).appendTo(this.$page);

		this.$container = $(`
			<div class="ai-chat-wrapper">
				<div class="ai-chat-feed"></div>
				<div class="ai-chat-input">
					<div class="ai-chat-input-shell">
						<textarea 
							class="form-control" 
							placeholder="${__("Ask about revenue, inventory, or any business insight...")}"
							rows="3"
						></textarea>
						<div class="ai-chat-actions">
							<div class="ai-chat-controls">
								<label class="checkbox">
									<input type="checkbox" class="ai-include-context" checked />
									<span>${__("Include business context")}</span>
								</label>
								<select class="form-control ai-days">
									<option value="7">7 ${__("days")}</option>
									<option value="30" selected>30 ${__("days")}</option>
									<option value="90">90 ${__("days")}</option>
								</select>
							</div>
							<div class="ai-chat-buttons">
								<button class="btn btn-default btn-summary">
									${__("Summary")}
								</button>
								<button class="btn btn-default btn-new">
									${__("New Chat")}
								</button>
								<button class="btn btn-primary btn-send">
									${__("Send Message")}
								</button>
							</div>
						</div>
					</div>
					<div class="ai-chat-input-footer">
						${__("ERPNext AI can make mistakes. Verify critical insights before acting.")}
					</div>
				</div>
			</div>
		`).appendTo(this.$page);

		this.$hero.find(".hero-suggestion").each((idx, el) => {
			$(el).data("message", suggestionCards[idx] && suggestionCards[idx].message);
		});

		this.$feed = this.$container.find(".ai-chat-feed");
		this.$textarea = this.$container.find("textarea");
		this.$includeContext = this.$container.find(".ai-include-context");
		this.$days = this.$container.find(".ai-days");
		this.$sendBtn = this.$container.find(".btn-send");
		this.$newBtn = this.$container.find(".btn-new");
		this.$summaryBtn = this.$container.find(".btn-summary");

		this._bindEvents();
	}

	_bindEvents() {
		this.$sendBtn.on("click", () => this.sendMessage());
		this.$newBtn.on("click", () => this.startNewConversation(true));
		this.$summaryBtn.on("click", () => this.requestSummary());
		
		this.$textarea.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
				e.preventDefault();
				this.sendMessage();
			}
		});

		this.$days.on("change", () => {
			this.days = cint(this.$days.val());
		});

		this.$includeContext.on("change", () => {
			this.includeContext = !!this.$includeContext.prop("checked");
			this._updateContextPreference();
		});

		this.$hero.find(".btn-hero-summary").on("click", () => this.requestSummary());
		this.$hero.find(".btn-hero-start").on("click", () => {
			this.$textarea.focus();
			this.$hero.addClass("hidden");
		});
		this.$hero.find(".hero-suggestion").on("click", (event) => {
			const $target = $(event.currentTarget);
			const prompt = ($target.data("message") || "").toString().trim();
			if (!prompt) return;

			this.$textarea.val(prompt);
			this.$textarea.focus();
			this.$hero.addClass("hidden");
		});
	}

	_updateContextPreference() {
		if (this.conversation && this.conversation.name) {
			const value = this.includeContext ? 1 : 0;
			this.conversation.include_context = value;
			
			frappe.call({
				method: "frappe.client.set_value",
				args: {
					doctype: "AI Conversation",
					name: this.conversation.name,
					fieldname: "include_context",
					value,
				},
				error: () => {
					frappe.show_alert({ 
						message: __("Failed to update context preference"), 
						indicator: "red" 
					});
				},
			});
		}
	}

	startNewConversation(force = false) {
		if (this.isSending) return;
		if (!force && this.conversation && (this.conversation.messages || []).length) {
			return;
		}

		this.clearTypingIndicator();
		this.clearPendingUserEcho();

		frappe.call({
			method: "erpnext_ai.api.create_ai_conversation",
			args: {
				include_context: this.includeContext ? 1 : 0,
				title: __("AI Conversation"),
			},
			freeze: false,
			callback: (r) => {
				this.conversation = r.message || null;
				this.renderConversation();
				this.$textarea.focus();
			},
		});
	}

	scrollFeedToBottom() {
		if (this.$feed && this.$feed.length) {
			this.$feed.scrollTop(this.$feed[0].scrollHeight);
		}
	}

	formatTimestamp(value) {
		if (!value) return "";
		try {
			if (typeof value === "string") {
				return frappe.datetime.str_to_user(value);
			}
			if (value instanceof Date) {
				const iso = value.toISOString().slice(0, 19).replace("T", " ");
				return frappe.datetime.str_to_user(iso);
			}
		} catch (e) {
			console.warn("Failed to format timestamp:", e);
		}
		return "";
	}

	renderMarkdown(text) {
		const content = text || "";
		try {
			return frappe.utils.markdown(content);
		} catch (e) {
			return frappe.utils.escape_html(content);
		}
	}

	createMessageElement(msg, options = {}) {
		const role = msg.role || "assistant";
		const roleLabel =
			role === "assistant" ? __("Assistant") :
			role === "user" ? __("You") : __("System");

		const bubbleClass = [
			"ai-chat-bubble",
			role,
			options.pending ? "pending" : "",
			options.error ? "error" : ""
		].filter(Boolean).join(" ");

		const messageClass = [
			"ai-chat-message",
			role,
			options.pending ? "is-pending" : "",
			options.error ? "is-error" : ""
		].filter(Boolean).join(" ");

		let body;
		if (options.pending) {
			const label = options.pendingLabel || __("Processing your request...");
			body = `
				<span class="typing-dots">
					<span></span><span></span><span></span>
				</span>
				<span>${frappe.utils.escape_html(label)}</span>
			`;
		} else {
			body = this.renderMarkdown(msg.content);
		}

		const timestamp = options.timestampOverride || msg.creation;
		const formattedTime = this.formatTimestamp(timestamp);
		const safeRoleLabel = frappe.utils.escape_html(roleLabel);
		const metaText = formattedTime
			? `${safeRoleLabel} · ${frappe.utils.escape_html(formattedTime)}`
			: safeRoleLabel;
		const metaMarkup = metaText ? `<div class="ai-chat-meta">${metaText}</div>` : "";

		const initialBase = (roleLabel || "U").charAt(0).toUpperCase() || "U";
		const rawAvatarInitial = role === "assistant" ? "AI" : initialBase;
		const safeAvatarInitial = frappe.utils.escape_html(rawAvatarInitial);
		const avatarMarkup = role === "system"
			? ""
			: `
				<div class="ai-chat-avatar ${role}">
					<span class="ai-chat-avatar-initial">${safeAvatarInitial}</span>
				</div>
			`;

		const contentClass = ["ai-chat-content", role === "system" ? "system" : ""]
			.filter(Boolean)
			.join(" ");
		const rowClass = ["ai-chat-row", role === "system" ? "system" : ""]
			.filter(Boolean)
			.join(" ");

		const $message = $(`
			<div class="${messageClass}">
				<div class="${rowClass}">
					${avatarMarkup}
					<div class="${contentClass}">
						<div class="${bubbleClass}">${body}</div>
						${metaMarkup}
					</div>
				</div>
			</div>
		`);

		if (!options.pending && msg.context_json) {
			const contextId = frappe.utils.get_random ?
				frappe.utils.get_random(10) :
				Math.random().toString(36).slice(2, 12);

			const $context = $(`
				<details class="ai-chat-context">
					<summary>${__("View Context Data")}</summary>
					<pre id="context-${contextId}"></pre>
				</details>
			`);

			const $meta = $message.find(".ai-chat-meta");
			if ($meta.length) {
				$meta.after($context);
			} else {
				$message.find(".ai-chat-content").append($context);
			}

			try {
				const parsed = JSON.parse(msg.context_json);
				$context.find("pre").text(JSON.stringify(parsed, null, 2));
			} catch (e) {
				$context.find("pre").text(msg.context_json);
			}
		}

		return $message;
	}

	clearPendingUserEcho() {
		if (this.$pendingUserEcho) {
			this.$pendingUserEcho.remove();
			this.$pendingUserEcho = null;
		}
	}

	clearTypingIndicator() {
		if (this.$typingIndicator) {
			this.$typingIndicator.remove();
			this.$typingIndicator = null;
		}
	}

	showTypingIndicator(label) {
		this.clearTypingIndicator();
		this.$hero.addClass("hidden");
		
		const indicatorLabel = label || __("Analyzing your data...");
		this.$typingIndicator = this.createMessageElement(
			{ role: "assistant", content: "" },
			{
				pending: true,
				pendingLabel: indicatorLabel,
				timestampOverride: frappe.datetime.now_datetime ? 
					frappe.datetime.now_datetime() : new Date(),
			}
		);

		this.$feed.append(this.$typingIndicator);
		this.scrollFeedToBottom();
	}

	renderErrorBubble(text) {
		const content = text || __("Unable to process your request at this time.");
		const $error = this.createMessageElement(
			{
				role: "assistant",
				content,
				creation: frappe.datetime.now_datetime ? 
					frappe.datetime.now_datetime() : new Date(),
			},
			{ error: true }
		);

		this.$feed.append($error);
		this.scrollFeedToBottom();
	}

	extractErrorMessage(err) {
		if (!err) return __("An unexpected error occurred");
		
		if (typeof err === "string") return err;
		if (err.message) return err.message;
		if (err.exc) return err.exc;
		
		if (err._server_messages) {
			try {
				const msgs = JSON.parse(err._server_messages);
				if (Array.isArray(msgs) && msgs.length) {
					return JSON.parse(msgs[0]).message || msgs[0];
				}
			} catch (e) {
				return err._server_messages;
			}
		}
		
		return __("Request failed");
	}

	fetchConversation() {
		if (!this.conversation || !this.conversation.name) {
			return Promise.resolve();
		}

		return frappe.call({
			method: "erpnext_ai.api.get_ai_conversation",
			args: { conversation_name: this.conversation.name },
		}).then((resp) => {
			if (resp && resp.message) {
				this.conversation = resp.message;
				this.renderConversation();
			}
		});
	}

	renderConversation() {
		this.$feed.empty();
		this.clearTypingIndicator();
		this.clearPendingUserEcho();
		
		const messages = (this.conversation && this.conversation.messages) || [];
		const hasMessages = !!messages.length;

		this.$page.toggleClass("chat-active", hasMessages);
		
		if (!hasMessages) {
			this.$hero.removeClass("hidden");
			return;
		}

		this.$hero.addClass("hidden");
		this.$includeContext.prop("checked", !!this.conversation.include_context);

		messages.forEach((msg) => {
			const $message = this.createMessageElement(msg);
			this.$feed.append($message);
		});

		this.scrollFeedToBottom();
	}

	sendMessage() {
		if (this.isSending) return;
		
		const message = (this.$textarea.val() || "").trim();
		if (!message) {
			frappe.show_alert({ 
				message: __("Please enter a message"), 
				indicator: "orange" 
			});
			return;
		}

		if (!this.conversation) {
			this.startNewConversation(true);
			return;
		}

		this.isSending = true;
		this._setButtonsDisabled(true);
		this.$hero.addClass("hidden");

		this.clearPendingUserEcho();
		this.$pendingUserEcho = this.createMessageElement(
			{
				role: "user",
				content: message,
				creation: frappe.datetime.now_datetime ? 
					frappe.datetime.now_datetime() : new Date(),
			},
			{ 
				timestampOverride: frappe.datetime.now_datetime ? 
					frappe.datetime.now_datetime() : new Date() 
			}
		);

		this.$feed.append(this.$pendingUserEcho);
		this.scrollFeedToBottom();
		this.showTypingIndicator(__("Generating response..."));

		frappe.call({
			method: "erpnext_ai.api.send_ai_message",
			args: {
				conversation_name: this.conversation.name,
				message,
				days: this.days,
			},
			freeze: false,
			callback: (r) => {
				this.clearPendingUserEcho();
				this.clearTypingIndicator();
				this.conversation = r.message || this.conversation;
				this.$textarea.val("");
				this.renderConversation();
			},
			always: () => {
				this.isSending = false;
				this._setButtonsDisabled(false);
				this.$textarea.focus();
			},
			error: (err) => {
				this.clearTypingIndicator();
				const errorText = this.extractErrorMessage(err);
				
				this.fetchConversation().finally(() => {
					this.renderErrorBubble(errorText);
					frappe.show_alert({
						message: errorText,
						indicator: "red",
					});
				});
			},
		});
	}

	_setButtonsDisabled(disabled) {
		this.$sendBtn.prop("disabled", disabled);
		this.$newBtn.prop("disabled", disabled);
		this.$summaryBtn.prop("disabled", disabled);
	}

	requestSummary() {
		if (this.isSending) return;

		const ensureConversation = () => {
			if (this.conversation) {
				return Promise.resolve();
			}
			
			return new Promise((resolve) => {
				frappe.call({
					method: "erpnext_ai.api.create_ai_conversation",
					args: { 
						include_context: this.includeContext ? 1 : 0, 
						title: __("Business Summary") 
					},
					callback: (r) => {
						this.conversation = r.message || null;
						resolve();
					},
				});
			});
		};

		this.isSending = true;
		this._setButtonsDisabled(true);

		ensureConversation()
			.then(() => {
				const requestText = __("Generate business summary for the last {0} days", [this.days]);
				
				return frappe.call({
					method: "erpnext_ai.api.append_ai_message",
					args: {
						conversation_name: this.conversation.name,
						role: "user",
						content: requestText,
					},
				}).then(() => requestText);
			})
			.then(() => {
				return frappe.call({
					method: "erpnext_ai.api.generate_admin_summary",
					args: { days: this.days },
					freeze: false,
				});
			})
			.then((r) => {
				const data = r.message || {};
				const output = data.output || __("Summary generation completed successfully.");
				
				return frappe.call({
					method: "erpnext_ai.api.append_ai_message",
					args: {
						conversation_name: this.conversation.name,
						role: "assistant",
						content: output,
					},
				}).then((resp) => {
					this.conversation = resp.message || this.conversation;
					this.renderConversation();
					
					if (data.report_name) {
						frappe.show_alert({
							message: __("Report {0} has been saved", [data.report_name]),
							indicator: "green",
						});
					}
				});
			})
			.finally(() => {
				this.isSending = false;
				this._setButtonsDisabled(false);
				this.clearTypingIndicator();
			});
	}
};
