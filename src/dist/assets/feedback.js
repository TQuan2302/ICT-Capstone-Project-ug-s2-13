/**
 * Flag Missing Object page.
 *
 * Page URL: /feedback/?name=<file name without extension>&t=<ms, videos only>.
 * It loads a clean frame (no detection boxes) from the server, lets the user draw
 * boxes with a class each, and sends them back to be saved as feedback data.
 *
 */

const params = new URLSearchParams(window.location.search);
const fileName = params.get("name");
const timeMs = params.has("t") ? parseInt(params.get("t"), 10) : null;

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const classSelect = document.getElementById("class_select");
const saveBtn = document.getElementById("save_btn");
const undoBtn = document.getElementById("undo_btn");
const clearBtn = document.getElementById("clear_btn");
const boxList = document.getElementById("box_list");
const messageBox = document.getElementById("message");
const warningBox = document.getElementById("warning");

const MIN_BOX_CSS_PX = 5;

let frameImage = null;
let boxes = []; // { x_min, y_min, x_max, y_max, class_name } in real image pixels
let dragStart = null;
let dragCurrent = null;
let saved = false;

function formatTime(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function showMessage(text, kind) {
  messageBox.textContent = text;
  messageBox.className = `alert alert-${kind}`;
  messageBox.hidden = false;
}

function clearMessage() {
  messageBox.hidden = true;
  messageBox.textContent = "";
}

/** How many real image pixels one on-screen pixel covers. */
function pixelScale() {
  const rect = canvas.getBoundingClientRect();
  return rect.width > 0 ? canvas.width / rect.width : 1;
}

/** Mouse position -> real image pixels, kept inside the picture. */
function toImagePoint(event) {
  const rect = canvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) * canvas.width) / rect.width;
  const y = ((event.clientY - rect.top) * canvas.height) / rect.height;
  return {
    x: Math.min(Math.max(x, 0), canvas.width),
    y: Math.min(Math.max(y, 0), canvas.height),
  };
}

function draw() {
  if (!frameImage) {
    return;
  }
  const scale = pixelScale();
  ctx.drawImage(frameImage, 0, 0);

  ctx.lineWidth = 3 * scale;
  ctx.font = `${14 * scale}px sans-serif`;
  ctx.textBaseline = "bottom";

  boxes.forEach((box) => {
    ctx.strokeStyle = "#ff3b30";
    ctx.fillStyle = "#ff3b30";
    ctx.strokeRect(box.x_min, box.y_min, box.x_max - box.x_min, box.y_max - box.y_min);
    const textY = box.y_min > 18 * scale ? box.y_min - 4 * scale : box.y_min + 18 * scale;
    ctx.fillText(box.class_name, box.x_min + 2 * scale, textY);
  });

  if (dragStart && dragCurrent) {
    ctx.strokeStyle = "#ffd60a";
    ctx.lineWidth = 2 * scale;
    ctx.setLineDash([6 * scale, 4 * scale]);
    ctx.strokeRect(
      Math.min(dragStart.x, dragCurrent.x),
      Math.min(dragStart.y, dragCurrent.y),
      Math.abs(dragCurrent.x - dragStart.x),
      Math.abs(dragCurrent.y - dragStart.y)
    );
    ctx.setLineDash([]);
  }
}

function refreshBoxList() {
  boxList.replaceChildren();
  boxes.forEach((box) => {
    const item = document.createElement("li");
    item.textContent = box.class_name;
    boxList.appendChild(item);
  });
  saveBtn.disabled = saved || boxes.length === 0;
  undoBtn.disabled = saved || boxes.length === 0;
  clearBtn.disabled = saved || boxes.length === 0;
}

function onPointerDown(event) {
  if (saved || !frameImage || event.button !== 0) {
    return;
  }
  clearMessage();
  canvas.setPointerCapture(event.pointerId);
  dragStart = toImagePoint(event);
  dragCurrent = dragStart;
  draw();
}

function onPointerMove(event) {
  if (!dragStart) {
    return;
  }
  dragCurrent = toImagePoint(event);
  draw();
}

function onPointerUp(event) {
  if (!dragStart) {
    return;
  }
  const end = toImagePoint(event);
  const minSize = MIN_BOX_CSS_PX * pixelScale();
  const x_min = Math.min(dragStart.x, end.x);
  const y_min = Math.min(dragStart.y, end.y);
  const x_max = Math.max(dragStart.x, end.x);
  const y_max = Math.max(dragStart.y, end.y);

  dragStart = null;
  dragCurrent = null;

  // Ignore tiny boxes (accidental clicks).
  if (x_max - x_min >= minSize && y_max - y_min >= minSize && classSelect.value) {
    boxes.push({ x_min, y_min, x_max, y_max, class_name: classSelect.value });
    refreshBoxList();
  }
  draw();
}

async function loadClasses() {
  const response = await fetch("/api/feedback/classes");
  if (!response.ok) {
    throw new Error("Could not load the class list.");
  }
  const classes = await response.json();

  // Group the classes by the model they belong to.
  const groups = new Map();
  classes.forEach((item) => {
    if (!groups.has(item.model)) {
      const group = document.createElement("optgroup");
      group.label = item.model.replaceAll("_", " ");
      groups.set(item.model, group);
      classSelect.appendChild(group);
    }
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.name;
    groups.get(item.model).appendChild(option);
  });
}

async function loadFrame() {
  const query = timeMs !== null && !Number.isNaN(timeMs) ? `?t=${timeMs}` : "";
  const response = await fetch(`/api/feedback/frame/${encodeURIComponent(fileName)}${query}`);
  if (!response.ok) {
    let detail = "Could not load the picture.";
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch (error) {
      // keep the default message
    }
    throw new Error(detail);
  }

  const isClean = response.headers.get("X-Frame-Clean") === "true";
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  await new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      frameImage = image;
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      resolve();
    };
    image.onerror = () => reject(new Error("Could not display the picture."));
    image.src = url;
  });

  if (!isClean) {
    warningBox.textContent =
      "Could not read the original un-annotated file, so this picture may still show " +
      "detection boxes. If you still have the original file, upload it again before flagging.";
    warningBox.hidden = false;
  }
  draw();
}

async function save() {
  clearMessage();
  saveBtn.disabled = true;

  try {
    const response = await fetch("/api/feedback/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: fileName, t_ms: timeMs, boxes }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof body.detail === "string" ? body.detail : "Could not save feedback.");
    }

    saved = true;
    const places = body.saved.map((item) => item.label).join(", ");
    showMessage(`Saved ${boxes.length} box(es) to the retrain feedback folder for: ${places}.`, "success");
    refreshBoxList();
  } catch (error) {
    showMessage(error.message, "danger");
    refreshBoxList();
  }
}

async function start() {
  if (!fileName) {
    showMessage("No file was chosen. Open a result and press Flag Missing Object.", "danger");
    return;
  }

  document.getElementById("file_name").textContent = fileName;
  if (timeMs !== null && !Number.isNaN(timeMs)) {
    document.getElementById("frame_time").textContent = `(frame at ${formatTime(timeMs)})`;
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  window.addEventListener("resize", draw);

  undoBtn.addEventListener("click", () => {
    boxes.pop();
    refreshBoxList();
    draw();
  });
  clearBtn.addEventListener("click", () => {
    boxes = [];
    refreshBoxList();
    draw();
  });
  saveBtn.addEventListener("click", save);

  refreshBoxList();

  try {
    await loadClasses();
    await loadFrame();
  } catch (error) {
    showMessage(error.message, "danger");
  }
}

start();

/** References: this script has been written with the help of AI (chatgpt, Claude, Grok)
 */