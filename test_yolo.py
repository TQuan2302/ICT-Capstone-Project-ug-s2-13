from ultralytics import YOLO

model = YOLO("yolo11n.pt")
results = model("https://ultralytics.com/images/bus.jpg", save=True)

print("YOLO setup works")