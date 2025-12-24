frappe.ui.form.on("AI Settings", {
  refresh(frm) {
    frm.trigger("sync_provider_ui");
  },
  api_provider(frm) {
    frm.trigger("sync_provider_ui");
  },
  sync_provider_ui(frm) {
    const provider = (frm.doc.api_provider || "OpenAI").trim() || "OpenAI";
    if (frm.doc.api_provider !== provider) {
      frm.set_value("api_provider", provider);
    }

    const openaiModels = ["gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini"];
    const geminiModels = ["gemini-2.5-flash"];

    const shouldShowOpenAI = provider === "OpenAI";
    frm.toggle_display("openai_api_key", shouldShowOpenAI);
    frm.toggle_display("gemini_api_key", !shouldShowOpenAI);

    const modelOptions = shouldShowOpenAI ? openaiModels : geminiModels;
    frm.set_df_property("openai_model", "options", modelOptions.join("\n"));

    if (!frm.doc.openai_model || !modelOptions.includes(frm.doc.openai_model)) {
      frm.set_value("openai_model", modelOptions[0]);
    }
  },
});
