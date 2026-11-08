const STORAGE_KEY = "roadsightJob";
let lastRenderedPhase = null;

/**
 * If a job is under process gets its state from storage, else returns null.
 */
function readJob() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
  } catch (error) {
    return null;
  }
}

function getExtension(filename) {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(0, dot) : filename;
}

function stageLabel(phase) {
  if (phase === "uploading") return "Uploading…";
  if (phase === "detecting") return "Detecting…";
  if (phase === "result") return "Getting result…";
  if (phase === "ready") return "Ready";
  return "Failed";
}

function barWidth(state) {
  if (state.phase === "uploading") {
    const pct = Number(state.uploadPercent) || 0;
    return Math.max(0, Math.min(20, pct * 0.2));
  }
  if (state.phase === "detecting") {
    const tick = Number(state.detectTick) || 0;
    return Math.max(20, Math.min(80, 20 + tick * 3));
  }
  if (state.phase === "result") return 90;
  return 100;
}

/**
 * Show detected media (image or video) or a message if no media was found.
 * Until its ready the media is hidden.
 */
function applyMedia(state) {
  const video = document.getElementById("job_video");
  const image = document.getElementById("job_image");
  const message = document.getElementById("job_media_message");
  if (!video || !image || !message) return;

  const media = state.phase === "ready" ? state.media : null;
  if (!media || !media.url) {
    if (video.getAttribute("src")) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
    video.style.display = "none";
    image.style.display = "none";
    image.removeAttribute("src");
    if (state.phase === "ready") {
      message.hidden = false;
      message.textContent = "Detection finished, but no detected file was saved.";
    } else {
      message.hidden = true;
      message.textContent = "";
    }
    return;
  }

  message.hidden = true;
  message.textContent = "";
  if (media.kind === "image") {
    video.style.display = "none";
    if (image.getAttribute("src") !== media.url) image.src = media.url;
    image.style.display = "inline-block";
    return;
  }

  image.style.display = "none";
  image.removeAttribute("src");
  if (video.getAttribute("src") !== media.url) {
    video.src = media.url;
    video.style.display = "block";
    video.load();
    video.onerror = () => {
      video.style.display = "none";
      message.hidden = false;
      message.textContent = "The detected video could not be played.";
    };
  } else {
    video.style.display = "block";
  }
}

/**
 * Updates job card so page matches the job state.
 */
function render(state) {
  const banner = document.getElementById("job_banner");
  const bar = document.getElementById("job_bar");
  const wrap = document.getElementById("job_progress");
  const label = document.getElementById("job_label");
  const detail = document.getElementById("job_detail");
  if (!banner || !bar || !wrap || !label || !detail || !state) return;

  const text = state.label || stageLabel(state.phase);
  const width = barWidth(state);
  const wasHidden = banner.hidden;
  banner.hidden = false;
  label.textContent = text;
  bar.textContent = text;
  bar.style.width = `${width}%`;
  wrap.setAttribute("aria-valuenow", String(Math.round(width)));

  if (state.phase === "ready") {
    bar.className = "progress-bar bg-success";
  } else if (state.phase === "error") {
    bar.className = "progress-bar bg-danger";
  } else {
    bar.className = "progress-bar progress-bar-striped progress-bar-animated";
  }

  if (state.phase === "error") {
    detail.textContent = state.error || "Detection failed.";
    detail.className = "mb-0 text-danger";
  } else if (state.fileLabel) {
    detail.textContent = state.fileLabel;
    detail.className = "mb-0 text-secondary";
  } else {
    detail.textContent = "";
    detail.className = "mb-0 text-secondary";
  }

  applyMedia(state);
  if (wasHidden || (state.phase === "ready" && lastRenderedPhase !== "ready")) {
    banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  lastRenderedPhase = state.phase;
}

/**
 * Save the job into memeory so when move page or refresh the job is still there,
 * this is what browser reads after a page refresh.
 * Sends the state to render() to update the page, based on current state.
 */
function save(state) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  render(state);
  return state;
}

/**
 * The server asks for a job's update every 3 seconds
 * If a job fails, update the job state to failed, so the browser doesn't keep polling.
 */
function fail(message) {
  const current = readJob() || {};
  save({
    ...current,
    phase: "error",
    label: "Failed",
    error: message,
    media: null,
  });
}

/**
 * Runs after after detection is finished. 
 * It fetches the result file and shows it on the card.
 */
async function loadResult(item) {
  const current = readJob() || {};
  save({
    ...current,
    phase: "result",
    label: "Getting result…",
    filename: item.filename,
    stem: item.stem,
    media: null,
  });

  let response;
  try {
    response = await fetch(`/detections/${encodeURIComponent(item.stem)}`);
  } catch (error) {
    fail("Detection finished, but the result could not be loaded.");
    return;
  }
  if (!response.ok) {
    fail("Detection finished, but the result could not be loaded.");
    return;
  }

  const data = await response.json();
  const latest = readJob() || {};
  save({
    ...latest,
    phase: "ready",
    label: "Ready",
    filename: item.filename,
    stem: item.stem,
    fileLabel: latest.fileLabel || item.filename,
    media: data.media || null,
    error: null,
  });
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/**
 * Watches the job's progress.
 * Polls the server every 3 seconds to check if the job is finished.
 */
async function watch(filename) {
  let detectTick = Number((readJob() || {}).detectTick) || 0;
  while (true) {
    let uploads;
    try {
      const response = await fetch("/uploads");
      if (!response.ok) throw new Error("status");
      uploads = await response.json();
    } catch (error) {
      await sleep(3000);
      continue;
    }

    const item = uploads.find((row) => row.filename === filename);
    if (item && item.status === "failed") {
      fail(`Detection failed for ${filename}.`);
      return;
    }
    if (item && item.status === "done") {
      await loadResult(item);
      return;
    }

    detectTick += 1;
    const current = readJob() || {};
    save({
      ...current,
      phase: "detecting",
      label: "Detecting…",
      filename,
      stem: current.stem || getExtension(filename),
      detectTick,
      media: null,
    });
    await sleep(3000);
  }
}

function beginUpload(fileLabel) {
  save({
    phase: "uploading",
    label: "Uploading…",
    uploadPercent: 0,
    detectTick: 0,
    filename: null,
    stem: null,
    fileLabel,
    media: null,
    error: null,
  });
}

function setUploadPercent(percent) {
  const current = readJob() || {};
  if (current.phase !== "uploading") return;
  save({
    ...current,
    phase: "uploading",
    label: "Uploading…",
    uploadPercent: Math.max(0, Math.min(100, percent)),
  });
}

function beginDetecting(filename) {
  const current = readJob() || {};
  save({
    ...current,
    phase: "detecting",
    label: "Detecting…",
    filename,
    stem: getExtension(filename),
    detectTick: 0,
    media: null,
    error: null,
  });
  return watch(filename);
}

/**
 * Resumes the job if it was stopped.
 * If the job is still uploading, it shows a message.
 * If the job is detecting or result, it starts watching again.
 */
function resume() {
  const state = readJob();
  if (!state || !state.phase) return;
  render(state);
  if (state.phase === "uploading") {
    fail("Upload stopped because the page changed. Start the upload again from Home.");
    return;
  }
  if ((state.phase === "detecting" || state.phase === "result") && state.filename) {
    watch(state.filename);
  }
}

window.RoadSightJob = {
  beginUpload,
  setUploadPercent,
  beginDetecting,
  fail,
};

resume();


// References: this script has been written with the help of AI (chatgpt, Claude, Grok)