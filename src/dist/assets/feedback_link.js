/**
 * Adds a "Flag Missing Object" button to the results page.
 *
 * It appears under the "Detected file" heading while a detected video or image is
 * shown. For a video it reads the time the video is paused on, so the feedback page
 * opens on that frame.
 */
(function () {
  const video = document.getElementById("detected_video");
  const image = document.getElementById("detected_image");
  if (!video && !image) {
    return;
  }

  const heading = Array.from(document.querySelectorAll("h3")).find(
    (item) => item.textContent.trim() === "Detected file"
  );
  if (!heading) {
    return;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.id = "flag_missing_btn";
  button.className = "btn btn-warning btn-sm mb-2";
  button.textContent = "Flag Missing Object";
  button.hidden = true;
  heading.insertAdjacentElement("afterend", button);

  /** The file name the result belongs to, read from the media address. */
  function nameFromSource(element) {
    const src = element ? element.getAttribute("src") : null;
    const match = src && src.match(/\/preview-stream\/([^?]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  function isShown(element) {
    return Boolean(element) && element.style.display !== "none" && element.hasAttribute("src");
  }

  function current() {
    if (isShown(video)) {
      return { kind: "video", name: nameFromSource(video) };
    }
    if (isShown(image)) {
      return { kind: "image", name: nameFromSource(image) };
    }
    return null;
  }

  function update() {
    const shown = current();
    button.hidden = !(shown && shown.name);
  }

  button.addEventListener("click", () => {
    const shown = current();
    if (!shown || !shown.name) {
      return;
    }
    let target = `/feedback/?name=${encodeURIComponent(shown.name)}`;
    if (shown.kind === "video") {
      video.pause();
      target += `&t=${Math.round(video.currentTime * 1000)}`;
    }
    window.location.href = target;
  });

  const observer = new MutationObserver(update);
  [video, image].forEach((element) => {
    if (element) {
      observer.observe(element, { attributes: true, attributeFilter: ["src", "style"] });
    }
  });
  update();
})();