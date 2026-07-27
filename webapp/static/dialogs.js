(() => {
  "use strict";

  function createButton(label, className = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function openDialog({
    eyebrow = "CONFIRM ACTION",
    title,
    message,
    fields = [],
    confirmLabel = "确认",
    danger = false,
  }) {
    return new Promise((resolve) => {
      const dialog = document.createElement("dialog");
      dialog.className = "action-dialog";
      const form = document.createElement("form");
      form.className = "dialog-card";

      const heading = document.createElement("div");
      const eyebrowNode = document.createElement("p");
      eyebrowNode.className = "eyebrow";
      eyebrowNode.textContent = eyebrow;
      const titleNode = document.createElement("h2");
      titleNode.textContent = title;
      heading.append(eyebrowNode, titleNode);
      form.append(heading);

      if (message) {
        const description = document.createElement("p");
        description.className = "dialog-message";
        description.textContent = message;
        form.append(description);
      }

      if (fields.length) {
        const fieldList = document.createElement("div");
        fieldList.className = "dialog-fields";
        for (const field of fields) {
          const label = document.createElement("label");
          label.textContent = field.label;
          const input = document.createElement("input");
          input.name = field.name;
          input.type = field.type || "text";
          input.value = String(field.value ?? "");
          if (field.min !== undefined) input.min = String(field.min);
          if (field.max !== undefined) input.max = String(field.max);
          if (field.step !== undefined) input.step = String(field.step);
          input.required = field.required !== false;
          label.append(input);
          fieldList.append(label);
        }
        form.append(fieldList);
      }

      const actions = document.createElement("div");
      actions.className = "dialog-actions";
      const cancel = createButton("取消");
      const submit = createButton(
        confirmLabel,
        danger ? "primary danger-button" : "primary",
      );
      submit.type = "submit";
      actions.append(cancel, submit);
      form.append(actions);
      dialog.append(form);
      document.body.append(dialog);

      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        dialog.close();
        dialog.remove();
        resolve(value);
      }

      cancel.addEventListener("click", () => finish(null));
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        finish(null);
      });
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) finish(null);
      });
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        finish(fields.length ? Object.fromEntries(new FormData(form)) : true);
      });

      dialog.showModal();
      const firstInput = form.querySelector("input");
      (firstInput || submit).focus();
      firstInput?.select();
    });
  }

  function ask(options) {
    return openDialog(options);
  }

  function collect(options) {
    return openDialog(options);
  }

  window.JobHuntDialog = {ask, collect};
})();
