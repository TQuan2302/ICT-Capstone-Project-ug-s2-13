let models = [];
let statusState = { running: false, result: null, logs: [], error: null };
let lastBusy = null;
let starting = false;

function setMessage(text, isError) {
  const message = document.getElementById("retrain_message");
  message.textContent = text;
  message.className = isError ? "text-danger mt-3 mb-0" : "text-secondary mt-3 mb-0";
}

function getEpochsValue() {
  const numEpochs = Number(document.getElementById("epochs").value);
  if (!Number.isFinite(numEpochs) || numEpochs < 1 || numEpochs > 200) {
    return 10;
  }
  return Math.round(numEpochs);
}

async function openFeedback(modelKey) {
  const response = await fetch(`/retrain/${encodeURIComponent(modelKey)}/open-feedback`, {
    method: "POST",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setMessage(payload.detail || "Error:Could not open the feedback folder.", true);
    return;
  }
  setMessage("Opened the feedback folder.", false);
}

async function startRetrain(modelKey) {
  if (starting || statusState.running) {
    return;
  }
  starting = true;
  const epochs = getEpochsValue();
  setMessage(`Starting training for ${modelKey} (${epochs} epochs)…`, false);
  renderModels();
  try {
    const response = await fetch(`/retrain/${encodeURIComponent(modelKey)}?epochs=${epochs}`, {
      method: "POST",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(payload.detail || "Could not start training.", true);
      return;
    }
    setMessage(`Training ${modelKey}. Logs update below.`, false);
    await loadStatus();
  } catch (error) {
    setMessage(error.message || "Could not reach the server.", true);
  } finally {
    starting = false;
    renderModels();
  }
}

// build model cards 
function renderModels() {
  const list = document.getElementById("model_list");
  list.replaceChildren();
  const busy = statusState.running || statusState.result || starting;

  models.forEach((model) => {
    const card = document.createElement("section");
    card.className = "p-3 border rounded-3 bg-white";

    const title = document.createElement("h2");
    title.className = "h5";
    title.textContent = model.label;
    card.appendChild(title);

    const counts = document.createElement("p");
    counts.className = "mb-1";
    counts.textContent = `Feedback: ${model.feedback}    Past data: ${model.train}    Validation: ${model.val}`;
    card.appendChild(counts);

    if (model.classes && model.classes.length) {
      const classes = document.createElement("p");
      classes.className = "text-secondary mb-1";
      classes.textContent = `Classes: ${model.classes.map((name) => name.split("_").join(" ")).join(", ")}`;
      card.appendChild(classes);
    }

    const reason = document.createElement("p");
    reason.className = model.ready ? "text-success mb-3" : "text-secondary mb-3";
    reason.textContent = model.reason || "Ready to retrain. Feedback and validation counts are high enough.";
    card.appendChild(reason);

    const actions = document.createElement("div");
    actions.className = "d-flex flex-wrap gap-2";

    const folderBtn = document.createElement("button");
    folderBtn.type = "button";
    folderBtn.className = "btn btn-outline-secondary";
    folderBtn.textContent = "Open feedback folder";
    folderBtn.disabled = statusState.running;
    folderBtn.addEventListener("click", () => openFeedback(model.key));

    const trainBtn = document.createElement("button");
    trainBtn.type = "button";
    trainBtn.className = "btn btn-primary";
    trainBtn.textContent = "Retrain";
    trainBtn.disabled = busy || !model.ready;
    trainBtn.addEventListener("click", () => {
      startRetrain(model.key).catch((error) => {
        setMessage(error.message || "Could not start training.", true);
      });
    });

    actions.appendChild(folderBtn);
    actions.appendChild(trainBtn);
    card.appendChild(actions);
    list.appendChild(card);
  });
}

/**
 * Every 3 seconds updates page with the latest logs, score (if exists).
 * If the state has changed, rebuild the model cards to show new counts, enable or disable buttons, ready or not ready status.
 */
function renderStatus() {
  const log = document.getElementById("retrain_log");
  log.textContent = statusState.logs && statusState.logs.length
    ? statusState.logs.join("\n")
    : "Training logs appear here.";

  const score = document.getElementById("score_box");
  const result = statusState.result;
  if (result) {
    score.hidden = false;
    score.replaceChildren();
    const headline = document.createElement("p");
    headline.className = "fw-semibold mb-1";
    headline.textContent = result.headline;
    const numbers = document.createElement("p");
    numbers.className = "mb-0";
    const oldMap = result.old && result.old.map != null ? result.old.map : 0;
    const newMap = result.new && result.new.map != null ? result.new.map : 0;
    numbers.textContent = `Current mAP ${oldMap}    New mAP ${newMap}    Suggested: ${result.suggested}`;
    score.appendChild(headline);
    score.appendChild(numbers);
  } else {
    score.hidden = true;
    score.replaceChildren();
  }

  document.getElementById("keep_btn").disabled = !result || statusState.running;
  document.getElementById("discard_btn").disabled = !result || statusState.running;
  document.getElementById("epochs").disabled = statusState.running || starting;
  if (statusState.error) {
    setMessage(statusState.error, true);
  }
  const busy = Boolean(statusState.running || statusState.result);
  if (busy !== lastBusy) {
    lastBusy = busy;
    renderModels();
  }
}

async function loadModels() {
  const response = await fetch("/retrain/models");
  if (!response.ok) {
    throw new Error("Could not load the models.");
  }
  models = await response.json();
  renderModels();
}

async function loadStatus() {
  const response = await fetch("/retrain/status");
  if (!response.ok) {
    return;
  }
  statusState = await response.json();
  renderStatus();
}

async function finish(action) {
  const response = await fetch(`/retrain/${action}`, { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setMessage(payload.detail || `Could not ${action} the result.`, true);
    return;
  }
  setMessage(action === "keep" ? "The live model was updated." : "The new weights were discarded.", false);
  await loadStatus();
  await loadModels();
}

document.getElementById("keep_btn").addEventListener("click", () => finish("keep"));
document.getElementById("discard_btn").addEventListener("click", () => finish("discard"));

window.addEventListener("load", () => {
  loadModels().catch((error) => setMessage(error.message, true));
  loadStatus().catch(() => { });
  window.setInterval(() => {
    loadStatus().catch(() => { });
  }, 3000);
});


// References: this script has been written with the help of AI (chatgpt, Claude, Grok)