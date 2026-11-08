let uploading_locked = false;

function showDetectionInProgress() {
  const detail = document.getElementById("job_detail");
  if (!detail) return;
  detail.textContent = "Wait for the current detection to finish.";
  detail.className = "mb-0 text-danger";
}

async function runUpload(file, gpxFile) {
  if (uploading_locked) {
    showDetectionInProgress();
    return;
  }
  uploading_locked = true;
  document.getElementById("imageFile").disabled = true;
  document.getElementById("videoFile").disabled = true;
  document.getElementById("gpxFile").disabled = true;
  try {
    window.RoadSightJob.beginUpload(file.name);
    const saved = await uploadFile(file, gpxFile);
    await window.RoadSightJob.beginDetecting(saved.filename);
  } catch (error) {
    window.RoadSightJob.fail(error.message);
  } finally {
    uploading_locked = false;
    document.getElementById("imageFile").disabled = false;
    document.getElementById("videoFile").disabled = false;
    document.getElementById("gpxFile").disabled = false;
    document.getElementById("imageFile").value = "";
    document.getElementById("videoFile").value = "";
    document.getElementById("gpxFile").value = "";
  }
}

/**
 * Upload the file to the server and updates the upload progress bar.
 */
function uploadFile(file, gpxFile) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload/video");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        window.RoadSightJob.setUploadPercent((event.loaded / event.total) * 100);
      }
    };
    xhr.onload = () => {
      let payload = {};
      try {
        payload = JSON.parse(xhr.responseText);
      } catch (error) {
        payload = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload);
        return;
      }
      const detail = payload.detail;
      reject(new Error(typeof detail === "string" ? detail : `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed. Check that the server is running."));

    const data = new FormData();
    data.append("file", file);
    if (gpxFile) {
      data.append("gpx", gpxFile);
    }
    xhr.send(data);
  });
}

/**
 * Waits for upload, if the upload is locked, show the detection in progress message.
 * If the upload is not locked, run the upload process.
 */
document.getElementById("imageFile").addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  if (uploading_locked) {
    event.target.value = "";
    showDetectionInProgress();
    return;
  }
  runUpload(file, null);
});

document.getElementById("videoFile").addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  if (uploading_locked) {
    event.target.value = "";
    showDetectionInProgress();
    return;
  }
  const gpxInput = document.getElementById("gpxFile");
  const gpxFile = gpxInput.files && gpxInput.files[0] ? gpxInput.files[0] : null;
  runUpload(file, gpxFile);
});


// References: this script has been written with the help of AI (chatgpt, Claude, Grok)