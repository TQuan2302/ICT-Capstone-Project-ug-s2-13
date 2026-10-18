## How to run the system 

# Method 1 - download the project folder 
1. python3 -m venv .venv
2. source .venv/bin/activate
3. python -m pip install --upgrade pip
4. pip install -r requirements.txt
5. cd src
6. python app.py

# Method 2 - MacOS
- build the executable file (if doesn't exist yet):
1. follow step 1-4 of method 1
2. bash build.sh
- The finished app would be dist/RoadSight.app, click on it to start the system 

# Method 3 - Windows
- build the executable file (if doesn't exist yet):
1. python -m venv .venv
2. .venv\Scripts\activate
3. python -m pip install --upgrade pip
4. python -m pip install -r requirements.txt
5. python -m pip install pyinstaller
6. python -m PyInstaller RoadSight.spec --clean --noconfirm
- The finished app would be dist\RoadSight\RoadSight.exe, click on it to start the system


Dataset Source :
Videos on Box shared by the client 
https://www.istockphoto.com/photos/sign-speed-winding-road-speed-limit-sign
https://universe.roboflow.com/azha007/australia-traffic-signv2/browse?queryText=class%3A%22Advisory+speed%22&pageSize=50&startingIndex=0&browseQuery=true