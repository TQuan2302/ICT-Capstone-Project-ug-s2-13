
//define HTML tags for the slider 
var confidenceSliderHtml = ""
    + '<div class="confidence-slider">'
    + '<div>Min confidence: <b id="confidence-value">0.00</b></div>'
    + '<input id="confidence-slider" type="range" min="0" max="100" value="0" step="1">'
    + '<input id="confidence-box" type="number" min="0" max="1" step="0.01" value="0.00">'
    + "</div>";

function addConfidenceSlider(map, trackedMarkers) {
    var sliderControl = L.control({position: "bottomleft"});

    sliderControl.onAdd = function () {
        var div = L.DomUtil.create("div");
        div.innerHTML = confidenceSliderHtml;
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        return div;
    };

    sliderControl.addTo(map);

    var slider = document.getElementById("confidence-slider");
    var box = document.getElementById("confidence-box"); 
    var label = document.getElementById("confidence-value");

    function applyConfidenceFilter() {
        var minConfidence = Number(slider.value) / 100;
        label.textContent = minConfidence.toFixed(2);
        box.value = minConfidence.toFixed(2); 

        trackedMarkers.forEach(function (item) {
            var alreadyInGroup = item.group.hasLayer(item.marker);
            //add a marker if the confidence is above the minConfidence
            if ((item.confidence >= minConfidence) && !alreadyInGroup) {
                item.group.addLayer(item.marker);
            }
            //remove a marker if the confidence is not above the minConfidence
            if (!(item.confidence >= minConfidence) && alreadyInGroup) {
                item.group.removeLayer(item.marker);
            }
        });
    }

    slider.addEventListener("input", applyConfidenceFilter);

    box.addEventListener("change", function(){
        var typed = Number(box.value); 

        if(Number.isNaN(typed)){
            typed = 0; 
        }

        if(typed < 0){
            typed = 0; 
        }

        if(typed > 1){
            typed = 1; 
        }
        slider.value = Math.round(typed * 100); 
        applyConfidenceFilter(); 
    })
}

//References: this script has been written with the help of AI (Cursor)