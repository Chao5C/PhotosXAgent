from datetime import datetime
from pathlib import Path

from PIL import Image

img = Image.new("RGB", (640, 480), (40, 120, 200))
exif = img.getexif()
exif[306] = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
exif[271] = "PhotosX"
exif[272] = "AgentCam"
path = Path("data/uploads/_sample.jpg")
path.parent.mkdir(parents=True, exist_ok=True)
img.save(path, "JPEG", exif=exif)
print(path)
