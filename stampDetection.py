python
import cv2
import numpy as np



# DETECT COLORED CIRCULAR STAMPS

def detect_stamp_regions(image_path):

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError("Could not open image")

    output = image.copy()

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    detections = []

    # =====================================================
    # RED STAMP MASK
    # =====================================================

    lower_red1 = np.array([0, 80, 50])
    upper_red1 = np.array([10, 255, 255])

    lower_red2 = np.array([170, 80, 50])
    upper_red2 = np.array([180, 255, 255])

    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)

    red_mask = cv2.bitwise_or(mask_red1, mask_red2)


    # =====================================================
    # BLUE STAMP MASK
    # =====================================================

    lower_blue = np.array([90, 80, 50])
    upper_blue = np.array([130, 255, 255])

    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)


    # =====================================================
    # GREEN STAMP MASK
    # =====================================================

    lower_green = np.array([35, 50, 50])
    upper_green = np.array([85, 255, 255])

    green_mask = cv2.inRange(hsv, lower_green, upper_green)


    # =====================================================
    # PROCESS ALL MASKS
    # =====================================================

    masks = [
        ("RED", red_mask, (0, 0, 255)),
        ("BLUE", blue_mask, (255, 0, 0)),
        ("GREEN", green_mask, (0, 255, 0))
    ]


    for label, mask, draw_color in masks:

        # Clean noise
        kernel = np.ones((5, 5), np.uint8)

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            kernel
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel
        )


        # =================================================
        # FIND CONTOURS
        # =================================================

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )


        for contour in contours:

            area = cv2.contourArea(contour)

            # Ignore tiny blobs
            if area < 1000:
                continue

            perimeter = cv2.arcLength(contour, True)

            if perimeter == 0:
                continue


            # =============================================
            # CIRCULARITY CHECK
            # =============================================

            circularity = (
                4 * np.pi * area
            ) / (perimeter * perimeter)


            # Perfect circle ≈ 1.0
            # Stamps usually 0.5+
            if circularity < 0.5:
                continue


            x, y, w, h = cv2.boundingRect(contour)

            detections.append({
                "label": label,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "area": area,
                "circularity": circularity
            })


            # Draw rectangle
            cv2.rectangle(
                output,
                (x, y),
                (x + w, y + h),
                draw_color,
                3
            )


            # Draw label
            cv2.putText(
                output,
                f"{label} STAMP",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                draw_color,
                2
            )


    return output, detections


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    image_path = "sample_document.png"

    result_image, detections = detect_stamp_regions(
        image_path
    )


    print("\n=== DETECTIONS ===")

    for d in detections:
        print(d)


    cv2.imshow("Detected Stamps", result_image)

    cv2.waitKey(0)

    cv2.destroyAllWindows()