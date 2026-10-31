/**
 * Turn a raw column name into a table heading.
 * "class_name" becomes "class name".
 */
function getColName(name) {
  return name.split("_").join(" ");
}

/**
 * Build an HTML table from a list of rows and column names
 */
function buildHtmlTable(table, rows, emptyMessage, colNames) {
  table.replaceChildren();

  const tableColumnsNames = rows && rows.length ? Object.keys(rows[0]) : (colNames || []);

  if (!tableColumnsNames.length) {
    const body = document.createElement("tbody");
    if (emptyMessage) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.textContent = emptyMessage;
      cell.className = "text-secondary";
      row.appendChild(cell);
      body.appendChild(row);
    }
    table.appendChild(body);
    return;
  }

  // build the table col header with column names
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  tableColumnsNames.forEach((colName) => {
    const th = document.createElement("th");
    th.textContent = getColName(colName);
    header.appendChild(th);
  });
  head.appendChild(header);
  table.appendChild(head);

  // build the body row with data rows
  // case 1 : there is no data 
  const body = document.createElement("tbody");
  body.className = "table-group-divider";
  if (!rows || rows.length === 0) {
    if (emptyMessage) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = tableColumnsNames.length;
      cell.textContent = emptyMessage;
      cell.className = "text-secondary";
      row.appendChild(cell);
      body.appendChild(row);
    }
    table.appendChild(body);
    return;
  }

  rows.forEach((record) => {
    const tr = document.createElement("tr");
    tableColumnsNames.forEach((column) => {
      const td = document.createElement("td");
      const value = record[column];
      td.textContent = value === null || value === undefined ? "" : String(value);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  table.appendChild(body);
}

/**
 * Set the download button to the given file path
 */
function displayDownload(downloadBtn, filePath) {
  if (!downloadBtn) {
    return;
  }
  if (!filePath) {
    downloadBtn.hidden = true;
    downloadBtn.removeAttribute("href");
    return;
  }
  downloadBtn.hidden = false;
  downloadBtn.href = filePath;
}

/**
 * Show the detection results for the selected video/image
 */
function showDetectionResult(detectionResult) {
  const video = document.getElementById("detected_video");
  const image = document.getElementById("detected_image");
  const message = document.getElementById("media_message");

  if (video) {
    video.onerror = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    video.style.display = "none";
  }
  if (image) {
    image.removeAttribute("src");
    image.style.display = "none";
  }

  if (!detectionResult || !detectionResult.url) {
    if (message) {
      message.textContent = "Error: There are no results to display.";
    }
    return;
  }

  if (detectionResult.kind === "image" && image) {
    image.src = detectionResult.url;
    image.style.display = "inline-block";
    if (message) {
      message.textContent = "";
    }
    return;
  }

  if (!video) {
    return;
  }

  video.src = detectionResult.url;
  video.style.display = "block";
  video.load();
  if (message) {
    message.textContent = "";
  }
  video.onerror = () => {
    video.style.display = "none";
    if (message) {
      message.textContent = "The detected video could not be played.";
    }
  };
}

/**
 * Load the selected file's results from the server and put them on the page.
 * Fill the counts report and the detection details table.
 * Point the CSV download buttons at their files.
 * Show the detected image or video below.
 */
function renderDetections(fileName) {
  const countsTable = document.getElementById("counts_table");
  const detailsTable = document.getElementById("detections_table");

  fetch(`/detections/${encodeURIComponent(fileName)}`)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Error: Could not find the report.");
      }
      return response.json();
    })
    .then((data) => {
      if (countsTable) {
        buildHtmlTable(countsTable, data.report, "", data.report_columns);
      }
      if (detailsTable) {
        buildHtmlTable(detailsTable, data.details, "No detection details found.", data.detail_columns);
      }
      displayDownload(document.getElementById("report_csv_link"), data.csv && data.csv.report);
      displayDownload(document.getElementById("details_csv_link"), data.csv && data.csv.details);
      showDetectionResult(data.media);
    })
    .catch(() => {
      if (countsTable) {
        buildHtmlTable(countsTable, [], "Error: Could not load the counts report.");
      }
      if (detailsTable) {
        buildHtmlTable(detailsTable, [], "Error: Could not load the detection details report.");
      }
      showDetectionResult(null);
    });
}

/**
 * every 5 seconds, update the list of finished detections as the webapp processes new uploads
 */
function renderFinishedDetectionsList() {
  const processedTable = document.getElementById("processed_table");
  if (!processedTable) {
    return;
  }

  const selectedCell = processedTable.querySelector("tr.table-active td");
  const selectedName = selectedCell ? selectedCell.textContent : "";

  fetch("/uploads")
    .then((response) => response.json())
    .then((list) => {
      processedTable.replaceChildren();
      list.filter((element) => element.status === "done").forEach((element) => {
        const row = processedTable.insertRow(-1);
        row.dataset.stem = element.stem;
        row.insertCell(0).textContent = element.filename;
        row.insertCell(1).textContent = element.date;
        if (element.filename === selectedName) {
          row.classList.add("table-active");
        }
      });
    });
}

window.addEventListener("load", () => {
  renderFinishedDetectionsList();
  window.setInterval(renderFinishedDetectionsList, 5000);
});

const processedTable = document.getElementById("processed_table");
if (processedTable) {
  processedTable.addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row || !processedTable.contains(row)) {
      return;
    }
    const fileName = row.dataset.stem || "";
    if (!fileName) {
      return;
    }
    processedTable.querySelectorAll("tr").forEach((item) => item.classList.remove("table-active"));
    row.classList.add("table-active");
    renderDetections(fileName);
  });
}


// References: this script has been written with the help of AI (chatgpt, Claude, Grok)