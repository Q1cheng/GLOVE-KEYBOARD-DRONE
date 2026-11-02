import cv2

for camera_id in range(6):
    camera = cv2.VideoCapture(camera_id, cv2.CAP_AVFOUNDATION)
    ok, frame = camera.read()

    if ok:
        height, width = frame.shape[:2]
        print(f"Camera ID {camera_id}: WORKING — {width}x{height}")
    else:
        print(f"Camera ID {camera_id}: unavailable")

    camera.release()