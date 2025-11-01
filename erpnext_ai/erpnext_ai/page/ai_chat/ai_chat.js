frappe.provide("erpnext_ai.pages");

frappe.pages["ai-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Assistant"),
		single_column: true,
	});

	if (page && typeof page.set_title === "function") {
		page.set_title("");
	}

	new erpnext_ai.pages.AIChat(page);
};

erpnext_ai.pages.AIChat = class AIChat {
	constructor(page) {
		this.page = page;
		this.conversation = null;
		this.days = 30;
		this.includeContext = true;
		this.isSending = false;
		this.isIdle = false;
		this.idleDelay = 8000;
		this.idleTimer = null;
		this.idleVideoReady = false;
		this.idleVideoPrimed = false;
		this.$idleVideo = null;
		this.$typingIndicator = null;
		this.$pendingUserEcho = null;
		this.$toolbar = null;

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
				--ai-chat-app-bg: #161616;
				--ai-chat-feed-bg: #161616;
				--ai-chat-panel: rgba(54, 54, 54, 0.85);
				--ai-chat-border: #363636;
				--ai-chat-text: #ffffff;
				--ai-chat-muted: rgba(255, 255, 255, 0.7);
				--ai-chat-assistant-bg: #363636;
				--ai-chat-user-bg: #161616;
				--ai-chat-user-text: #ffffff;
				--ai-chat-shadow: 0 -12px 32px rgba(22, 22, 22, 0.6);
				--ai-chat-input-bg: #161616;
				--ai-chat-input-border: #363636;
				--ai-chat-accent: #363636;
				--ai-chat-accent-hover: #161616;
				--ai-chat-button-text: #ffffff;
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
				background: linear-gradient(145deg, #363636, #161616);
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
				background: rgba(54, 54, 54, 0.6);
				color: #ffffff;
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
				background: rgba(54, 54, 54, 0.8);
				border-color: #363636;
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
				background: rgba(54, 54, 54, 0.9);
				border-color: rgba(54, 54, 54, 0.8);
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

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .hero-actions .btn-primary,
			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-buttons .btn-primary {
				box-shadow: 0 6px 18px rgba(22, 22, 22, 0.45);
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
				border-color: #363636;
				color: var(--ai-chat-text);
				background: rgba(22, 22, 22, 0.35);
			}

			.ai-chat-hero.hidden {
				display: none;
			}

			.ai-chat-wrapper {
				flex: 1;
				min-height: 0;
				display: flex;
				flex-direction: column;
				background: #232323;
				border-radius: 22px;
				border: 1px solid rgba(148, 163, 184, 0.18);
				overflow: hidden;
				position: relative;
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04),
					0 24px 60px rgba(15, 23, 42, 0.18);
			}

			.ai-chat-container.chat-active .ai-chat-wrapper {
				height: 100%;
				display: grid;
				grid-template-rows: 1fr auto;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-wrapper {
				border-color: #363636;
			}

			.ai-chat-feed {
				flex: 1;
				overflow-y: auto;
				overflow-x: hidden;
				padding: 1.5rem 0 2rem;
				display: flex;
				flex-direction: column;
				background: transparent;
				position: relative;
				scrollbar-width: thin;
				scrollbar-color: rgba(148, 163, 184, 0.4) transparent;
				z-index: 1;
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

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-feed {
				scrollbar-color: rgba(255, 255, 255, 0.25) transparent;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-feed::-webkit-scrollbar-thumb {
				background: rgba(255, 255, 255, 0.25);
			}

			.ai-chat-idle-layer {
				position: absolute;
				inset: 0;
				pointer-events: none;
				overflow: hidden;
				z-index: 0;
			}

			.ai-chat-idle-layer video {
				position: absolute;
				inset: 0;
				width: 100%;
				height: 100%;
				object-fit: cover;
				opacity: 0;
				pointer-events: none;
				transition: opacity 0.6s ease;
				filter: saturate(0.8) brightness(1.1);
			}

			.ai-chat-wrapper.is-idle .ai-chat-idle-layer video {
				opacity: 0.7;
			}

			.ai-chat-feed::after {
				content: "";
				height: 1rem;
				flex-shrink: 0;
			}

			.ai-chat-message {
				padding: 0 1.75rem;
				position: relative;
				z-index: 1;
			}

			.ai-chat-message.is-entering {
				animation: ai-chat-message-in 0.36s ease forwards;
			}

			.ai-chat-message.is-entering .ai-chat-bubble {
				animation: ai-chat-bubble-in 0.36s ease forwards;
			}

			.ai-chat-row {
				display: flex;
				align-items: flex-start;
				gap: 1.25rem;
				padding: 1.25rem 0;
				border-bottom: 1px solid rgba(148, 163, 184, 0.2);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-row {
				border-color: rgba(54, 54, 54, 0.6);
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
				background: linear-gradient(135deg, #161616, #363636);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-avatar.assistant {
				background: linear-gradient(140deg, #363636, #161616);
				box-shadow: 0 8px 20px rgba(22, 22, 22, 0.5);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-avatar.user {
				background: linear-gradient(145deg, #161616, #363636);
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
				padding: 1.2rem 1.4rem;
				border-radius: 24px;
				font-size: 0.98rem;
				line-height: 1.65;
				max-width: 100%;
				word-wrap: anywhere;
				position: relative;
				background: rgba(236, 238, 241, 0.46);
				color: var(--ai-chat-text);
				border: 1px solid rgba(15, 23, 42, 0.05);
				box-shadow: none;
				overflow: hidden;
			}

			.ai-chat-bubble:hover {
				transform: translateY(-1px);
				box-shadow:
					0 18px 46px rgba(17, 24, 39, 0.28),
					inset 0 4px 11px rgba(255, 255, 255, 0.52),
					inset 0 -9px 16px rgba(17, 24, 39, 0.2);
				border-color: rgba(255, 255, 255, 0.3);
			}

			.ai-chat-bubble::before,
			.ai-chat-bubble::after {
				content: '';
				position: absolute;
				pointer-events: none;
				border-radius: 50%;
				filter: blur(8px);
				opacity: 0.85;
				display: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble {
				background: rgba(26, 28, 32, 0.5);
				border: 1px solid rgba(255, 255, 255, 0.03);
				box-shadow: none;
				color: rgba(236, 242, 255, 0.9);
			}

			.ai-chat-bubble.assistant {
				background: rgba(236, 238, 241, 0.46);
				border: 1px solid rgba(15, 23, 42, 0.05);
				box-shadow: none;
				color: rgba(15, 23, 42, 0.88);
			}

			.ai-chat-bubble.assistant::before {
				display: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble.assistant {
				background: rgba(26, 28, 32, 0.5);
				border: 1px solid rgba(255, 255, 255, 0.03);
				color: rgba(236, 242, 255, 0.9);
			}

			.ai-chat-bubble.user {
				background: rgba(240, 241, 244, 0.47);
				border: 1px solid rgba(15, 23, 42, 0.05);
				box-shadow: none;
				color: rgba(28, 32, 46, 0.88);
			}

			.ai-chat-bubble.user::before {
				display: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-bubble.user {
				background: rgba(23, 24, 28, 0.5);
				border: 1px solid rgba(255, 255, 255, 0.03);
				color: rgba(236, 242, 255, 0.9);
			}

			.ai-chat-bubble.system {
				background: transparent;
				color: var(--ai-chat-muted);
				padding: 0.75rem 0;
			}

			.ai-chat-bubble.pending {
				min-width: 90px;
				min-height: 46px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				padding: 0.75rem 1.2rem;
				background: rgba(236, 238, 241, 0.32);
				border: 1px solid rgba(15, 23, 42, 0.05);
			}

			.ai-chat-bubble.pending .typing-dots {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				gap: 0.35rem;
			}

			.ai-chat-bubble.pending .typing-dots span {
				width: 0.48rem;
				height: 0.48rem;
				border-radius: 50%;
				background: rgba(148, 163, 184, 0.72);
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
				background: #161616;
				border-color: #363636;
				color: #ffffff;
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

			@keyframes ai-chat-message-in {
				from {
					transform: translateY(8px);
					opacity: 0;
				}
				to {
					transform: translateY(0);
					opacity: 1;
				}
			}

			@keyframes ai-chat-bubble-in {
				from {
					transform: translateY(12px) scale(0.98);
					opacity: 0;
				}
				to {
					transform: translateY(0) scale(1);
					opacity: 1;
				}
			}

			@keyframes ai-chat-button-press {
				0% {
					transform: scale(1);
				}
				40% {
					transform: scale(0.9);
				}
				100% {
					transform: scale(1);
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

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-context summary {
				color: var(--ai-chat-text);
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
				background: rgba(54, 54, 54, 0.75);
				color: #ffffff;
			}

			.ai-chat-input {
				padding: 1.05rem clamp(1rem, 3vw, 1.5rem) 1.3rem;
				border-top: none;
				background: transparent;
				display: flex;
				flex-direction: column;
				gap: 0.75rem;
				position: sticky;
				bottom: 0;
				left: 0;
				right: 0;
				z-index: 5;
				backdrop-filter: blur(8px);
				-webkit-backdrop-filter: blur(8px);
			}

			.ai-chat-container.chat-active .ai-chat-input {
				padding: 0.9rem clamp(1rem, 3vw, 1.35rem) 1.1rem;
			}

			.ai-chat-input-shell {
				background: rgba(20, 22, 26, 0.35);
				border: 1px solid rgba(255, 255, 255, 0.05);
				border-radius: 22px;
				padding: 0.65rem clamp(1.35rem, 4vw, 2rem);
				display: flex;
				flex-direction: column;
				gap: 0.75rem;
				box-shadow: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-input-shell {
				box-shadow: none;
				background: rgba(20, 22, 26, 0.35);
				border-color: rgba(255, 255, 255, 0.06);
			}

			.ai-chat-composer {
				display: flex;
				align-items: flex-end;
				gap: 0.75rem;
			}

			.ai-chat-input textarea {
				width: 100%;
				height: 34px;
				min-height: 34px;
				max-height: 34px;
				resize: none;
				overflow-y: auto;
				border-radius: 0;
				padding: 0;
				font-size: 0.92rem;
				line-height: 1.45;
				background: transparent;
				border: none;
				color: var(--ai-chat-text);
				font-family: inherit;
			}

			.ai-chat-input textarea::placeholder {
				color: var(--ai-chat-muted);
				opacity: 0.85;
			}

			.ai-chat-input textarea:focus {
				outline: none;
				box-shadow: none;
			}

			.ai-chat-composer .btn-send {
				width: 44px;
				height: 44px;
				flex-shrink: 0;
				border-radius: 14px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				padding: 0;
				transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
			}

			.ai-chat-composer .btn-send .ai-icon {
				width: 18px;
				height: 18px;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-composer .btn-send {
				background: #363636;
				border-color: #363636;
				color: #ffffff;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-composer .btn-send:hover,
			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-composer .btn-send:focus {
				box-shadow: 0 10px 24px rgba(22, 22, 22, 0.45);
			}

			.ai-chat-composer .btn-send:hover,
			.ai-chat-composer .btn-send:focus {
				transform: translateY(-1px);
				box-shadow: 0 10px 24px rgba(58, 61, 66, 0.25);
				outline: none;
			}

			.ai-chat-toolbar {
				display: flex;
				justify-content: flex-end;
				align-items: center;
				gap: 0.75rem;
				margin-bottom: 0.5rem;
			}

			.ai-chat-toolbar .btn-round {
				width: 40px;
				height: 40px;
				border-radius: 50%;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				padding: 0;
				border: 1px solid var(--ai-chat-border);
				background: var(--ai-chat-input-bg);
				color: var(--ai-chat-text);
				box-shadow: 0 6px 18px rgba(58, 61, 66, 0.18);
				transition: transform 0.15s ease, box-shadow 0.15s ease;
			}

			.ai-chat-toolbar .btn-round .ai-icon,
			.ai-chat-toolbar .btn-round svg {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 18px;
				height: 18px;
				stroke: currentColor;
				fill: none;
				stroke-width: 2;
				stroke-linecap: round;
				stroke-linejoin: round;
			}

			.ai-chat-toolbar .btn-context .ai-icon-dollar {
				font-size: 0.95rem;
				font-weight: 600;
				width: auto;
				height: auto;
			}

			.ai-chat-toolbar .btn-context.is-active {
				background: var(--ai-chat-accent);
				color: var(--ai-chat-button-text);
				border-color: var(--ai-chat-accent);
			}

			.ai-chat-toolbar .btn-round.btn-primary {
				background: var(--ai-chat-accent);
				color: var(--ai-chat-button-text);
				border-color: var(--ai-chat-accent);
			}

			.ai-chat-toolbar .btn-round:hover,
			.ai-chat-toolbar .btn-round:focus {
				transform: translateY(-1px);
				box-shadow: 0 8px 20px rgba(58, 61, 66, 0.24);
				outline: none;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-toolbar .btn-round {
				background: rgba(54, 54, 54, 0.85);
				border-color: #363636;
				color: var(--ai-chat-text);
				box-shadow: 0 6px 18px rgba(22, 22, 22, 0.4);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-toolbar .btn-context.is-active {
				background: #363636;
				border-color: #363636;
				color: #ffffff;
				box-shadow: 0 6px 18px rgba(22, 22, 22, 0.5);
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-toolbar .btn-round.btn-primary {
				background: var(--ai-chat-accent);
				color: var(--ai-chat-button-text);
				border-color: #363636;
			}

			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-toolbar .btn-round:hover,
			html:is([data-theme="dark"], [data-theme-mode="dark"]) .ai-chat-toolbar .btn-round:focus {
				box-shadow: 0 8px 20px rgba(22, 22, 22, 0.45);
			}

			.ai-chat-toolbar .btn-round.is-pressing,
			.ai-chat-composer .btn-send.is-pressing {
				animation: ai-chat-button-press 0.32s ease forwards;
			}

			.ai-chat-meta {
				display: flex;
				justify-content: flex-end;
				align-items: center;
				gap: 0.75rem;
				flex-wrap: wrap;
				font-size: 0.85rem;
				color: var(--ai-chat-muted);
				margin-bottom: 0.6rem;
			}

			.ai-chat-meta label {
				display: inline-flex;
				align-items: center;
				gap: 0.5rem;
				margin: 0;
			}

			.ai-chat-meta input[type="checkbox"] {
				width: 16px;
				height: 16px;
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

				.ai-chat-toolbar {
					justify-content: space-between;
					gap: 0.5rem;
				}

				.ai-chat-toolbar .btn-round {
					width: 38px;
					height: 38px;
				}

				.ai-chat-meta {
					justify-content: space-between;
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

		const contextIcon = `
			<span class="ai-icon ai-icon-dollar" aria-hidden="true">$</span>`;
		const newIcon = `
			<svg class="ai-icon" viewBox="0 0 24 24" aria-hidden="true">
				<path d="M12 20h9"></path>
				<path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path>
			</svg>`;
		const sendIcon = `
			<svg class="ai-icon" viewBox="0 0 24 24" aria-hidden="true">
				<line x1="22" y1="2" x2="11" y2="13"></line>
				<polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
			</svg>`;

		this.$page = $('<div class="ai-chat-container"></div>').appendTo(this.page.body);
		this.$hero = $();

		this.$container = $(`
			<div class="ai-chat-wrapper">
				<div class="ai-chat-toolbar">
					<button type="button" class="btn btn-round btn-default btn-context" title="${__("Include business context")}" aria-pressed="true">
						${contextIcon}
					</button>
					<button type="button" class="btn btn-round btn-default btn-new" title="${__("Start New Chat")}">
						${newIcon}
					</button>
				</div>
				<div class="ai-chat-feed"></div>
				<div class="ai-chat-input">
					<div class="ai-chat-input-shell">
						<div class="ai-chat-composer">
							<textarea 
								class="form-control"
								rows="3"
							></textarea>
							<button type="button" class="btn btn-round btn-primary btn-send" title="${__("Send Message")}">
								${sendIcon}
							</button>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.$page);

		this.$feed = this.$container.find(".ai-chat-feed");
		console.log("[AI Chat] Feed element found:", this.$feed.length > 0, this.$feed);

		this.$idleLayer = $('<div class="ai-chat-idle-layer" aria-hidden="true"></div>').prependTo(this.$container);
		const idleVideoUrl = (frappe.utils && frappe.utils.get_url)
			? frappe.utils.get_url("/assets/erpnext_ai/videos/suv.MP4")
			: "/assets/erpnext_ai/videos/suv.MP4";
		console.log("[AI Chat] Idle video URL:", idleVideoUrl);

		this.$idleVideo = $(`
			<video class="ai-chat-idle-video" muted playsinline loop preload="auto" aria-hidden="true">
				<source src="${idleVideoUrl}" type="video/mp4" />
			</video>
		`).appendTo(this.$idleLayer);
		console.log("[AI Chat] Video jQuery element created:", this.$idleVideo.length > 0);

		const idleVideoEl = this.$idleVideo.get(0);
		console.log("[AI Chat] Video DOM element:", idleVideoEl);

		if (idleVideoEl) {
			idleVideoEl.muted = true;
			idleVideoEl.loop = true;
			idleVideoEl.playsInline = true;
			console.log("[AI Chat] Video properties set");

			try {
				idleVideoEl.addEventListener("loadeddata", () => {
					console.log("[AI Chat] Video loadeddata event");
					this.idleVideoReady = true;
				});
				idleVideoEl.addEventListener("canplaythrough", () => {
					console.log("[AI Chat] Video canplaythrough event");
					this.idleVideoReady = true;
				});
				idleVideoEl.addEventListener("error", (event) => {
					console.error("[AI Chat] Video error:", event, "code:", idleVideoEl.error?.code);
				});
				idleVideoEl.load();
				console.log("[AI Chat] Video load() called");

				// Verify video in DOM
				setTimeout(() => {
					const check = document.querySelector('.ai-chat-idle-video');
					console.log("[AI Chat] Video exists in DOM:", !!check, check);
				}, 1000);
			} catch (err) {
				console.error("[AI Chat] Video setup failed:", err);
			}
		} else {
			console.error("[AI Chat] Failed to get video DOM element!");
		}

		this.$textarea = this.$container.find("textarea");
		this.$toolbar = this.$container.find(".ai-chat-toolbar");
		this.$contextBtn = this.$toolbar.find(".btn-context");
		this.$days = this.$container.find(".ai-days");
		this.$sendBtn = this.$container.find(".btn-send");
		this.$newBtn = this.$toolbar.find(".btn-new");

		this._syncContextToggle();
		this._bindEvents();
		this._recordActivity();
	}

	_bindEvents() {
		this.$sendBtn.on("click", () => {
			this._playButtonPress(this.$sendBtn);
			this._recordActivity();
			this.sendMessage();
		});

		this.$newBtn.on("click", () => {
			this._playButtonPress(this.$newBtn);
			this._recordActivity();
			this.startNewConversation(true);
		});

		this.$contextBtn.on("click", () => {
			this._playButtonPress(this.$contextBtn);
			this._recordActivity();
			this.includeContext = !this.includeContext;
			this._syncContextToggle();
			this._updateContextPreference();
		});
		
		this.$textarea.on("keydown", (e) => {
			this._recordActivity();
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
				e.preventDefault();
				this._playButtonPress(this.$sendBtn);
				this.sendMessage();
			}
		});
		this.$textarea.on("input", () => this._recordActivity());
		this.$feed.on("scroll", () => this._recordActivity());

		this.$days.on("change", () => {
			this.days = cint(this.$days.val());
		});

	}

	_playButtonPress($btn) {
		if (!$btn || !$btn.length || $btn.prop("disabled")) {
			return;
		}

		if ($btn.hasClass("is-pressing")) {
			return;
		}

		const clear = () => $btn.removeClass("is-pressing");
		$btn.addClass("is-pressing");
		$btn.one("animationend.ai-button", clear);
		setTimeout(clear, 360);
	}

	_recordActivity() {
		this._exitIdleState();
		this._clearIdleTimer();
		this._ensureIdleVideoPrimed();

		this.idleTimer = setTimeout(() => {
			this._enterIdleState();
		}, this.idleDelay);
	}

	_clearIdleTimer() {
		if (this.idleTimer) {
			clearTimeout(this.idleTimer);
			this.idleTimer = null;
		}
	}

	_ensureIdleVideoPrimed() {
		if (this.idleVideoPrimed) return;

		const videoEl = this.$idleVideo && this.$idleVideo.get ? this.$idleVideo.get(0) : null;
		if (!videoEl) return;

		try {
			const playPromise = videoEl.play();
			if (playPromise && typeof playPromise.then === "function") {
				playPromise
					.then(() => {
						try {
							videoEl.pause();
							videoEl.currentTime = 0;
						} catch (err) {
							console.warn("Idle video prime reset failed", err);
						}
						this.idleVideoPrimed = true;
					})
					.catch(() => {});
			} else {
				videoEl.pause();
				videoEl.currentTime = 0;
				this.idleVideoPrimed = true;
			}
		} catch (err) {
			console.warn("Idle video prime failed", err);
		}
	}

	_enterIdleState() {
		console.log("[AI Chat] _enterIdleState called, isIdle:", this.isIdle, "videoReady:", this.idleVideoReady);
		if (this.isIdle) return;
		if (!this.idleVideoReady) {
			console.log("[AI Chat] Video not ready yet, retrying in 500ms");
			this._clearIdleTimer();
			this.idleTimer = setTimeout(() => this._enterIdleState(), 500);
			return;
		}

		this._clearIdleTimer();
		this.isIdle = true;
		this.$container.addClass("is-idle");
		console.log("[AI Chat] is-idle class added to container");

		const videoEl = this.$idleVideo && this.$idleVideo.get ? this.$idleVideo.get(0) : null;
		console.log("[AI Chat] Attempting to play video, element:", videoEl);
		if (videoEl) {
			try {
				const playPromise = videoEl.play();
				if (playPromise && typeof playPromise.catch === "function") {
					playPromise
						.then(() => {
							console.log("[AI Chat] ✅ Idle video playing successfully!");
						})
						.catch((err) => {
							console.error("[AI Chat] ❌ Video play rejected:", err);
						});
				}
			} catch (err) {
				console.error("[AI Chat] Failed to play idle video:", err);
			}
		} else {
			console.error("[AI Chat] No video element found for playback!");
		}
	}

	_exitIdleState() {
		if (!this.isIdle) return;
		console.log("[AI Chat] _exitIdleState called - stopping video");
		this._clearIdleTimer();
		this.isIdle = false;
		this.$container.removeClass("is-idle");

		const videoEl = this.$idleVideo && this.$idleVideo.get ? this.$idleVideo.get(0) : null;
		if (videoEl) {
			try {
				videoEl.pause();
				videoEl.currentTime = 0;
				console.log("[AI Chat] Video paused and reset");
			} catch (err) {
				console.warn("Failed to reset idle video", err);
			}
		}
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

	_syncContextToggle() {
		if (!this.$contextBtn || !this.$contextBtn.length) return;

		const isActive = !!this.includeContext;
		const labelBase = __("Include business context");
		const stateLabel = isActive ? __("On") : __("Off");
		const title = `${labelBase} (${stateLabel})`;

		this.$contextBtn.toggleClass("is-active", isActive);
		this.$contextBtn.attr("aria-pressed", isActive ? "true" : "false");
		this.$contextBtn.attr("aria-label", title);
		this.$contextBtn.attr("title", title);
	}

	startNewConversation(force = false) {
		if (this.isSending) return;
		this._recordActivity();

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
				this._recordActivity();
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
			body = `
				<span class="typing-dots">
					<span></span><span></span><span></span>
				</span>
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

		if (options.animate) {
			const applyAnimation = () => {
				if (!$message || !$message.length) return;
				$message.addClass("is-entering");
				const clear = () => $message.removeClass("is-entering");
				$message.one("animationend.ai-chat-enter", clear);
				setTimeout(clear, 450);
			};

			if (typeof window !== "undefined" && window.requestAnimationFrame) {
				window.requestAnimationFrame(applyAnimation);
			} else {
				applyAnimation();
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
		this._recordActivity();
		
		const indicatorLabel = label || "";
		this.$typingIndicator = this.createMessageElement(
			{ role: "assistant", content: "" },
			{
				pending: true,
				pendingLabel: indicatorLabel,
				timestampOverride: frappe.datetime.now_datetime ? 
					frappe.datetime.now_datetime() : new Date(),
				animate: true
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
			{ error: true, animate: true }
		);

		this.$feed.append($error);
		this.scrollFeedToBottom();
		this._recordActivity();
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

	renderConversation(options = {}) {
		const animateLatest = !!options.animateLatest;

		this.$feed.empty();

		this.clearTypingIndicator();
		this.clearPendingUserEcho();
		
		const messages = (this.conversation && this.conversation.messages) || [];
		const hasMessages = !!messages.length;

		if (this.conversation && typeof this.conversation.include_context !== "undefined") {
			this.includeContext = !!this.conversation.include_context;
			this._syncContextToggle();
		}

		this.$page.toggleClass("chat-active", hasMessages);
		
		if (!hasMessages) {
			this.$hero.removeClass("hidden");
			return;
		}

		this.$hero.addClass("hidden");

		messages.forEach((msg, idx) => {
			const shouldAnimate = animateLatest && idx === messages.length - 1;
			const createOptions = shouldAnimate ? { animate: true } : {};
			const $message = this.createMessageElement(msg, createOptions);
			this.$feed.append($message);
		});

		this.scrollFeedToBottom();
		this._recordActivity();
	}

	sendMessage() {
		if (this.isSending) return;
		
		const message = (this.$textarea.val() || "").trim();
		this._recordActivity();

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

		const originalMessage = message;
		this.$textarea.val("");

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
					frappe.datetime.now_datetime() : new Date(),
				animate: true
			}
		);

		this.$feed.append(this.$pendingUserEcho);
		this.scrollFeedToBottom();
			this.showTypingIndicator("");

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
				this.renderConversation({ animateLatest: true });
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
					if (!this.$textarea.val()) {
						this.$textarea.val(originalMessage);
					}
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
					this.renderConversation({ animateLatest: true });
					
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
