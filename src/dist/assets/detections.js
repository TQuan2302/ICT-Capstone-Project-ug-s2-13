
function render_detections_for_file(file_name) {
  let detections_table = document.getElementById("detections_table");

  $.get(`/detections/${file_name}`, function (data) {
    console.log(data);
  });
}

function build_detection_list() {
  let processed_table = document.getElementById("processed_table");

  $.get("/detections-list", function (list) {
    list.forEach((element) => {
      console.log(`Name: ${element['name']}, Date: ${element['date']}`);
      const newRow = processed_table.insertRow(-1);

      const nameCell = newRow.insertCell(0);
      const dateCell = newRow.insertCell(1);

      nameCell.textContent = element['name'];
      dateCell.textContent = element['date'];
    });
  });
}

/* Functions on window load */
window.addEventListener("load", () => {
  console.log("page has loaded");

  console.log("Building list of processed videos")
  build_detection_list();
});

$("#processed_table").on('click', 'tr', function () {
  const video_name = $(this).find('td').eq(0).text();

  render_detections_for_file(video_name);
});
