function render_detections_for_file(file_name) {
  const detections_table = document.getElementById("detections_table");

  $.get(`/detections/${file_name}`, function (data) {
    detections_table.replaceChildren();

    const body = document.createElement('tbody');
    body.className = "table-group-divider";

    if (data['details'].length > 0) {
      column_categories = Object.keys(data['details'][0]);

      const head = document.createElement('thead');
      const header = document.createElement('tr');

      column_categories.forEach(name => {
        const th = document.createElement('th');
        th.textContent = name;
        header.appendChild(th);
      });
      head.appendChild(header);
      detections_table.appendChild(head);

      data['details'].forEach(detection => {
        const tr = document.createElement('tr');
        column_categories.forEach(category => {
          td = document.createElement('td');
          td.textContent = detection[category];
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
    } else {
      const message = document.createElement('h3');
      message.textContent = "There are no detections associated with the selected file";
      message.className = "text-secondary";
      detections_table.appendChild(message);
    }

    detections_table.appendChild(body);
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
