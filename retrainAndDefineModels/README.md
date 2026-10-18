# ICT-Capstone-Project-1-2

## Project Setup for YOLO in VS Code using WSL Ubuntu

This project uses **VS Code with WSL Ubuntu** and a local Python virtual environment to install and run **Ultralytics YOLO**.

We use this setup so that all dependencies stay inside the project folder instead of being installed globally on the computer. This makes the project cleaner, easier to manage, and more consistent for all team members.

---

## 1. Open the project in VS Code using WSL

Open the GitHub repository in **VS Code** and make sure it is running in **WSL Ubuntu**.

You can check this in the bottom-left corner of VS Code. It should say something like:

```bash
WSL: Ubuntu
````

This is important because all commands below are meant to be run inside the WSL Linux environment.

---

## 2. Install Python tools in WSL

Open a terminal in VS Code and run:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

This installs the required Python tools:

* `python3`
* `pip`
* `venv`

---

## 3. Create a virtual environment inside the project

From the root of the repository, run:

```bash
python3 -m venv .venv
```

This creates a local virtual environment called `.venv` inside the project folder.

A virtual environment keeps project packages isolated, which helps avoid conflicts with other Python projects on the machine.

---

## 4. Activate the virtual environment

Run the following command:

```bash
source .venv/bin/activate
```

If the activation works, the terminal should show `(.venv)` at the start of the command line.

Example:

```bash
(.venv) yosep@LAPTOP:~/ICT-Capstone-Project-1-2$
```

This means the virtual environment is active and ready to use.

---

## 5. Upgrade pip

After activating the environment, run:

```bash
python -m pip install --upgrade pip
```

This updates `pip` to the latest version inside the virtual environment.

---

## 6. Install Ultralytics YOLO

Install Ultralytics with:

```bash
pip install ultralytics
```

This installs the Ultralytics package, which includes YOLO models and tools for prediction, training, and testing.

---

## 7. Make VS Code use the virtual environment

Even if the terminal is already using `.venv`, VS Code should also use the same Python interpreter for running scripts and providing editor support.

### Steps

1. Press `Ctrl + Shift + P`
2. Search for `Python: Select Interpreter`
3. Choose the interpreter that looks like:

```bash
.venv/bin/python
```

If the interpreter option does not appear, install the **Python extension by Microsoft** in VS Code first.

---

## 8. Git ignore rules

The repository already includes a `.gitignore` file.

This prevents local environment files and generated YOLO outputs from being tracked by Git, including:

- `.venv/`
- `runs/`
- `datasets/`
- `*.pt`
- `*.onnx`
- `__pycache__/`
- `*.pyc`

Team members only need to pull the latest version of the repository to get these rules.

---
## 9. Check Git status

Run:

```bash
git status
```

If `.venv` does **not** appear in the output, that means Git is not tracking it, which is correct.

In our current setup, `.venv` was already not being tracked, so no extra removal step was needed.



## 11. Check that Ultralytics is installed

To confirm that Ultralytics was installed correctly, run:

```bash
pip show ultralytics
```

If installation was successful, this will show package information.

If it says the package is not found, run:

```bash
pip install ultralytics
```

---

## 12. First YOLO test

Create a file called:

```bash
test_yolo.py
```

Put this code inside it:

```python
from ultralytics import YOLO

model = YOLO("yolo11n.pt")
results = model("https://ultralytics.com/images/bus.jpg", save=True)

print("YOLO setup works")
```

Then run:

```bash
python test_yolo.py
```

If everything is working correctly, YOLO will:

* download the small pretrained model
* run detection on the test image
* save the output in a `runs/` folder
* print:

```bash
YOLO setup works
```

This confirms that the setup is working properly.

---

## 13. Suggested project structure

A simple and clean structure for the technical side of this project is shown below:

```bash
ICT-Capstone-Project-1-2/
│
├── .venv/
├── .gitignore
├── README.md
├── requirements.txt
├── data/
│   ├── raw_videos/
│   ├── extracted_frames/
│   └── labels/
├── scripts/
│   ├── test_yolo.py
│   ├── extract_frames.py
│   └── predict_video.py
└── runs/
```

### Notes

* `.venv/` should stay local and should not be pushed to GitHub
* `runs/` stores YOLO outputs and should also be ignored
* `data/` stores raw videos, extracted frames, and labels
* `scripts/` stores Python scripts for testing and processing

---

## 14. Recreating the setup on another machine

If another team member clones the repository, they can repeat the setup with these commands:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install ultralytics
```

If a `requirements.txt` file is added later, dependencies can also be installed using:

```bash
pip install -r requirements.txt
```

---

## 15. Current setup status

The project setup currently includes:

* VS Code running in WSL Ubuntu
* a local `.venv` created inside the repository
* the `.venv` environment activated successfully
* a `.gitignore` file created
* Git confirmed that `.venv` is not being tracked

This means the basic Python and YOLO environment setup is ready.

# Custom Roadway Element Training Guide

This guide is for training a custom **object detection** model for one roadway element, such as:

- pole
- traffic light
- traffic sign
- tree

## Important
This workflow is for **object detection only**.

It works best for objects that can be boxed with bounding boxes.

Examples:
- poles
- signs
- traffic lights
- trees

Some elements like:
- footpaths
- lanes
- bike lanes

may need **segmentation** instead of object detection.

---

## 1. Folder structure

Create this structure in the repo:

```text
datasets/
  element_name/
    images/
      train/
      val/
    labels/
      train/
      val/
    element_name.yaml

models/
  yolov8n.pt
  element_name_best.pt

scripts/
  train_element.py
  test_element.py
````

### Example for poles

```text
datasets/
  pole/
    images/
      train/
      val/
    labels/
      train/
      val/
    poles.yaml

models/
  yolov8n.pt
  pole_best.pt
```

---

## 2. Annotate in Roboflow

1. Create a new project

2. Choose **Object Detection**

3. Create **one class** for your element
   Example:

   * `pole`
   * `traffic_light`
   * `sign`

4. Upload your images

5. Annotate all objects using bounding boxes

6. Split the dataset into:

   * train
   * valid
   * test

Recommended split:

* 80% train
* 10% valid
* 10% test

---

## 3. Export dataset

Export the dataset in:

* **YOLOv8**
  or
* **YOLO11**

Then download and extract it.

---
## 4. Prepare the dataset inside the repo

After exporting the dataset from Roboflow, use the preparation script to split and copy the dataset into the project structure.

Expected Roboflow export structure:

```text
train/
  images/
  labels/

Run the dataset preparation script:

python scripts/prepare_detection_dataset.py (you can copy the ones on the root file to your own scripts file)

Before running it, update these fields inside the script:

ELEMENT_NAME
SOURCE_IMAGES
SOURCE_LABELS

The script will automatically create and fill:

datasets/<element_name>/images/train
datasets/<element_name>/images/val
datasets/<element_name>/labels/train
datasets/<element_name>/labels/val

This script is intended for object detection tasks only.

---

## 5. Create the YAML file

### Example: `datasets/pole/poles.yaml`

```yaml id="z4e1aa"
path: datasets/pole
train: images/train
val: images/val

names:
  0: pole
```

Change the class name if your element is different.

---

## 6. Train the model

### Example: `scripts/train_element.py`

```python id="l2gd1e"
from ultralytics import YOLO

def main():
    model = YOLO("models/yolov8n.pt")

    model.train(
        data="datasets/pole/poles.yaml",
        epochs=50,
        imgsz=640
    )

if __name__ == "__main__":
    main()
```

Run:

```bash id="nuf1rt"
source .venv/bin/activate
python scripts/train_element.py
```

---

## 7. Save the best model

After training, YOLO will create a folder inside:

```text
runs/detect/
```

The important file is usually:

```text
runs/detect/trainX/weights/best.pt
```

Copy it into `models/`.

### Example for poles

```bash id="5y9diz"
cp runs/detect/trainX/weights/best.pt models/pole_best.pt
```

Replace `trainX` with the actual folder name, such as:

* `train`
* `train2`
* `train3`

---

## 8. Test the model

### Example: `scripts/test_element.py`

```python id="hgz7li"
from ultralytics import YOLO

def main():
    model = YOLO("models/pole_best.pt")

    results = model(
        "datasets/pole/images/val",
        save=True
    )

    print("Testing complete")

if __name__ == "__main__":
    main()
```

Run:

```bash id="8r1ca6"
python scripts/test_element.py
```

Check the saved output images in `runs/detect/`.

---

## 9. Standalone inference file

If needed, create a standalone file like:

* `detect_pole.py`
* `detect_sign.py`
* `detect_traffic_light.py`

This file should:

* load the trained model
* run on image or video
* save the annotated result

---

## 10. Can multiple models be used in one app?

Yes.

The system can use multiple separate trained models, for example:

* `pole_best.pt`
* `traffic_light_best.pt`
* `sign_best.pt`

The app can run them one by one on the same uploaded video and combine all detections into one final output.

However, separate `.pt` files cannot be automatically merged into one model without retraining.

---

## 11. Files that should usually be shared

Minimum useful files:

* trained model
  Example: `models/pole_best.pt`
* inference file
  Example: `detect_pole.py`

Training scripts and YAML files are useful, but not strictly required just for running inference.



