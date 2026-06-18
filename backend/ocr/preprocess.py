"""Image preprocessing for prescription OCR (OpenCV).

Full pipeline for messy mobile photos: document detection + perspective
correction -> resize/super-resolution -> grayscale -> deskew -> rotation
correction -> denoise -> brightness normalization -> CLAHE contrast -> sharpen.

Two outputs:
* ``prepare_for_deep_model`` -> natural grayscale (EasyOCR/Paddle/TrOCR/DocTR/
  Vision/Gemini). Deep models are HURT by hard binarization.
* ``prepare_for_classic`` -> adds adaptive thresholding for Tesseract.

Every step is defensive: any failure degrades gracefully and returns the best
image available (or the original path).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

_MAX_EDGE = 2200
_MIN_EDGE = 1000


def _read(image_path: str) -> "np.ndarray":
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    return img


# ---------- geometry: document detection + perspective correction ----------
def _perspective_correct(img: "np.ndarray") -> "np.ndarray":
    """Find the largest 4-point contour (the page) and flatten it."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edged = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 180)
    edged = cv2.dilate(edged, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return img
    biggest = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(biggest) < 0.25 * w * h:  # not a full page; skip
        return img
    peri = cv2.arcLength(biggest, True)
    approx = cv2.approxPolyDP(biggest, 0.02 * peri, True)
    if len(approx) != 4:
        return img
    pts = approx.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect = np.array([
        pts[np.argmin(s)], pts[np.argmin(diff)],
        pts[np.argmax(s)], pts[np.argmax(diff)],
    ], dtype="float32")
    (tl, tr, br, bl) = rect
    wA, wB = np.linalg.norm(br - bl), np.linalg.norm(tr - tl)
    hA, hB = np.linalg.norm(tr - br), np.linalg.norm(tl - bl)
    maxW, maxH = int(max(wA, wB)), int(max(hA, hB))
    if maxW < 200 or maxH < 200:
        return img
    dst = np.array([[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, M, (maxW, maxH))


def _resize_to_band(img: "np.ndarray") -> "np.ndarray":
    h, w = img.shape[:2]
    longest = max(h, w)
    scale = 1.0
    if longest > _MAX_EDGE:
        scale = _MAX_EDGE / longest
    elif longest < _MIN_EDGE:
        scale = _MIN_EDGE / longest
    if scale != 1.0:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
    return img


def _super_resolve(img: "np.ndarray") -> "np.ndarray":
    """Use EDSR/FSRCNN if a model file is present, else high-quality cubic 2x."""
    h, w = img.shape[:2]
    if max(h, w) >= _MIN_EDGE:
        return img
    model_dir = Path(__file__).resolve().parent / "sr_models"
    for name, key, scale in [("FSRCNN_x2.pb", "fsrcnn", 2), ("EDSR_x2.pb", "edsr", 2)]:
        mp = model_dir / name
        if mp.exists() and hasattr(cv2, "dnn_superres"):
            try:
                sr = cv2.dnn_superres.DnnSuperResImpl_create()
                sr.readModel(str(mp))
                sr.setModel(key, scale)
                return sr.upsample(img)
            except Exception:  # noqa: BLE001
                break
    return cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


# ---------- rotation + skew ----------
def _orientation_correct(gray: "np.ndarray") -> "np.ndarray":
    """Coarse 0/90/180/270 correction using Tesseract OSD if available."""
    try:
        import pytesseract  # type: ignore

        osd = pytesseract.image_to_osd(gray)
        rot = int(next(l for l in osd.splitlines() if "Rotate:" in l).split(":")[1])
        if rot:
            k = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(rot)
            if k is not None:
                return cv2.rotate(gray, k)
    except Exception:  # noqa: BLE001
        pass
    return gray


def _deskew(gray: "np.ndarray") -> "np.ndarray":
    inv = cv2.bitwise_not(gray)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if coords.shape[0] < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5 or abs(angle) > 20:
        return gray
    h, w = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# ---------- photometric: denoise, brightness, contrast, sharpen ----------
def _normalize_brightness(gray: "np.ndarray") -> "np.ndarray":
    """Flatten uneven lighting / shadows by dividing out the background."""
    bg = cv2.medianBlur(gray, 41)
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def _enhance(gray: "np.ndarray") -> "np.ndarray":
    den = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    den = _normalize_brightness(den)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    out = clahe.apply(den)
    # Unsharp mask for crisper strokes.
    blur = cv2.GaussianBlur(out, (0, 0), 3)
    out = cv2.addWeighted(out, 1.5, blur, -0.5, 0)
    return out


def _common(image_path: str) -> "np.ndarray":
    img = _read(image_path)
    img = _perspective_correct(img)
    img = _super_resolve(img)
    img = _resize_to_band(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = _orientation_correct(gray)
    gray = _deskew(gray)
    gray = _enhance(gray)
    return gray


def prepare_for_deep_model(image_path: str, out_dir: str) -> str:
    if cv2 is None:
        return image_path
    try:
        gray = _common(image_path)
        out = str(Path(out_dir) / (Path(image_path).stem + "_deep.png"))
        cv2.imwrite(out, gray)
        return out
    except Exception:  # noqa: BLE001
        return image_path


def prepare_for_classic(image_path: str, out_dir: str) -> str:
    if cv2 is None:
        return image_path
    try:
        gray = _common(image_path)
        thr = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
        )
        out = str(Path(out_dir) / (Path(image_path).stem + "_classic.png"))
        cv2.imwrite(out, thr)
        return out
    except Exception:  # noqa: BLE001
        return image_path
