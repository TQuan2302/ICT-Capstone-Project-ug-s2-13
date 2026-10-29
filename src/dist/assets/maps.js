function open_map(url) {
  window.open(url, "_blank", "popup,width=1200,height=800");
}

function build_map_list() {
  const map_table = document.getElementById("map_table");

  $.get("/map-list", function (list) {
    if (list.length === 0) {
      const row = map_table.insertRow(-1);
      const cell = row.insertCell(0);
      cell.colSpan = 2;
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
    });
  });
}

window.addEventListener("load", () => {
  build_map_list();
});

$("#map_table").on("click", "tr", function () {
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
