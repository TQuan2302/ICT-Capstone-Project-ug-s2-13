function open_map(url) {
  window.open(url, "_blank", "popup,width=1200,height=800");
}

function build_map_list() {
  const map_table = document.getElementById("map_table");
  map_table.replaceChildren();

  $.get("/map-list", function (list) {
    if (list.length === 0) {
      const row = map_table.insertRow(-1);
      const cell = row.insertCell(0);
      cell.colSpan = 3;
      cell.className = "text-secondary";
      cell.textContent = "No videos with map data";
      return;
    }

    list.forEach((element) => {
      const newRow = map_table.insertRow(-1);
      newRow.dataset.name = element["name"];
      newRow.style.cursor = "pointer";

      const nameCell = newRow.insertCell(0);
      const dateCell = newRow.insertCell(1);
      nameCell.textContent = element["name"];
      dateCell.textContent = element["date"];

      const deleteCell = newRow.insertCell(2);
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "btn btn-sm text-danger fw-bold p-0 px-2 delete-entry";
      deleteButton.textContent = "X";
      deleteButton.dataset.name = element["name"];
      deleteCell.appendChild(deleteButton);
    });
  });
}

window.addEventListener("load", () => {
  build_map_list();
});

$("#map_table").on("click", ".delete-entry", function (event) {
  event.stopPropagation();
  const video_name = this.dataset.name;
  if (!video_name) {
    return;
  }
  if (!window.confirm(`Delete ${video_name}? This also removes its detection result.`)) {
    return;
  }

  fetch(`/detections/${encodeURIComponent(video_name)}`, { method: "DELETE" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Could not delete the map.");
      }
      build_map_list();
    });
});

$("#map_table").on("click", "tr", function (event) {
  if ($(event.target).closest(".delete-entry").length) {
    return;
  }
  const video_name = this.dataset.name;
  if (!video_name) {
    return;
  }

  $("#map_table tr").removeClass("table-active");
  $(this).addClass("table-active");
  open_map(`/map/${encodeURIComponent(video_name)}`);
});

$("#show_all_maps").on("click", function () {
  $("#map_table tr").removeClass("table-active");
  open_map("/map/all");
});

// References: this script has been written with the help of AI (Cursor)