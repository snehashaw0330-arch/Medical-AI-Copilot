"""AI-powered Image Quality Assessment for prescription photos (OpenCV only).

Runs *before* the OCR pipeline so the user can be warned about — and fix — a
bad photo before wasting a slow OCR pass on it. Every metric is computed with
OpenCV/NumPy alone (no extra dependencies) and degrades gracefully: any single
failed metric falls back to a neutral value instead of breaking the report.

Metrics computed
----------------
* Blur score      — variance of the Laplacian (focus measure; higher = sharper)
* Brightness      — mean luminance (0..255)
* Contrast        — standard deviation of luminance
* Sharpness       — Tenengrad (mean squared Sobel gradient magnitude)
* Noise level     — Immerkaer sigma estimate (std of a Laplacian convolution)
* Resolution      — width x height + megapixels
* Rotation angle  — dominant page rotation from Hough lines (degrees)
* Skew angle      — text-baseline skew from the min-area rectangle (degrees)

Each raw metric is mapped to a 0..100 sub-score; the weighted mean is the
overall quality score (0..100). Recommendations are derived from the sub-scores
so the guidance always matches the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore


# Below this overall score (0..100) we warn the user before starting OCR.
QUALITY_WARN_THRESHOLD = 60.0

# Sub-score weights (must sum to 1.0). Focus/sharpness dominate because they
# matter most for OCR; geometry (rotation/skew) is correctable so it weighs less.
_WEIGHTS = {
    "sharpness": 0.30,   # blur + Tenengrad combined below
    "brightness": 0.15,
    "contrast": 0.18,
    "noise": 0.15,
    "resolution": 0.12,
    "geometry": 0.10,    # rotation + skew combined below
}


# ----------------------------------------------------------------------------
# small scoring helpers
# ----------------------------------------------------------------------------
def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def _ramp(value: float, low: float, high: float) -> float:
    """Linearly map ``value`` in [low, high] to a 0..100 score (clamped)."""
    if high == low:
        return 100.0
    return _clamp((value - low) / (high - low) * 100.0)


def _window(value: float, lo_bad: float, lo_good: float, hi_good: float, hi_bad: float) -> float:
    """Trapezoidal score: 100 inside [lo_good, hi_good], ramping to 0 at the bad ends."""
    if value <= lo_bad or value >= hi_bad:
        return 0.0
    if lo_good <= value <= hi_good:
        return 100.0
    if value < lo_good:
        return _ramp(value, lo_bad, lo_good)
    return 100.0 - _ramp(value, hi_good, hi_bad)


# ----------------------------------------------------------------------------
# individual metric computations (each defensive)
# ----------------------------------------------------------------------------
def _blur_variance(gray: "np.ndarray") -> float:
    """Variance of the Laplacian — the classic focus/blur measure."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _tenengrad(gray: "np.ndarray") -> float:
    """Mean squared Sobel gradient magnitude (edge strength / sharpness)."""
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def _noise_sigma(gray: "np.ndarray") -> float:
    """Immerkaer (1996) fast noise standard-deviation estimate."""
    h, w = gray.shape[:2]
    if h < 3 or w < 3:
        return 0.0
    mask = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    conv = cv2.filter2D(gray.astype(np.float64), -1, mask)
    sigma = np.sum(np.abs(conv)) * np.sqrt(0.5 * np.pi) / (6.0 * (w - 2) * (h - 2))
    return float(sigma)


def _rotation_angle(gray: "np.ndarray") -> float:
    """Dominant page rotation in degrees via Hough lines (range roughly -45..45)."""
    edges = cv2.Canny(gray, 60, 180, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=200)
    if lines is None:
        return 0.0
    angles: list[float] = []
    for rho_theta in lines[:120]:
        theta = float(rho_theta[0][1])
        deg = np.degrees(theta) - 90.0  # 0 == horizontal lines
        # Fold into [-45, 45]; we only care about deviation from axis-aligned.
        deg = ((deg + 45.0) % 90.0) - 45.0
        angles.append(deg)
    if not angles:
        return 0.0
    return float(round(np.median(angles), 2))


def _skew_angle(gray: "np.ndarray") -> float:
    """Text-baseline skew (small tilt) via the min-area rectangle of dark pixels."""
    inv = cv2.bitwise_not(gray)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if coords.shape[0] < 50:
        return 0.0
    angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
    if angle < -45:
        angle = 90.0 + angle
    elif angle > 45:
        angle = angle - 90.0
    return float(round(angle, 2))


# ----------------------------------------------------------------------------
# report assembly
# ----------------------------------------------------------------------------
@dataclass
class QualityReport:
    """Plain dataclass mirror of the API schema (kept dependency-free here)."""

    overall_score: float
    rating: str
    passed: bool
    threshold: float
    metrics: dict = field(default_factory=dict)
    subscores: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _rating(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


def _recommendations(sub: dict[str, float], m: dict, brightness: float) -> list[str]:
    """Actionable, user-facing guidance derived from the sub-scores."""
    recs: list[str] = []
    if sub["sharpness"] < 55:
        recs.append("Image looks blurry — hold the camera steady and let it focus before capturing.")
    if brightness < 80:
        recs.append("Increase lighting — the photo is too dark to read reliably.")
    elif brightness > 200:
        recs.append("Reduce glare / lighting — the photo is overexposed and washed out.")
    if sub["contrast"] < 55:
        recs.append("Low contrast — avoid shadows and capture the prescription on a plain background.")
    if sub["noise"] < 55:
        recs.append("Image is noisy/grainy — improve lighting instead of using digital zoom.")
    if sub["resolution"] < 55:
        recs.append("Resolution is low — move closer or capture the prescription at higher quality.")
    if abs(m["rotation_angle"]) > 10:
        recs.append("Rotate the image upright — the page appears significantly tilted.")
    elif abs(m["skew_angle"]) > 5:
        recs.append("Straighten the page — the text lines are skewed.")
    # Shadow heuristic: dark overall but with high contrast variance hints at shadows.
    if 80 <= brightness < 120 and sub["contrast"] >= 70 and sub["brightness"] < 70:
        recs.append("Remove shadows — even out the lighting across the whole page.")
    if not recs:
        recs.append("Image quality looks good for OCR.")
    return recs


def assess_image_quality(
    image_path: str,
    threshold: float = QUALITY_WARN_THRESHOLD,
) -> QualityReport:
    """Analyze an image and return a full quality report (0..100 overall score).

    Never raises for image-content reasons: an unreadable file raises
    ``ValueError`` (so the route can return 400), but any individual metric
    failure degrades to a neutral value so a partial report is still returned.
    """
    if cv2 is None:  # OpenCV unavailable — report is unknown, do not block OCR.
        return QualityReport(
            overall_score=100.0,
            rating="Unknown",
            passed=True,
            threshold=threshold,
            warnings=["OpenCV is not installed; quality assessment was skipped."],
            recommendations=["Quality assessment unavailable — proceeding without it."],
        )

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    warnings: list[str] = []

    def _safe(fn, default: float) -> float:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{fn.__name__} failed ({exc}); used a neutral value.")
            return default

    blur = _safe(lambda: _blur_variance(gray), 0.0)
    brightness = _safe(lambda: float(np.mean(gray)), 128.0)
    contrast = _safe(lambda: float(np.std(gray)), 0.0)
    sharpness = _safe(lambda: _tenengrad(gray), 0.0)
    noise = _safe(lambda: _noise_sigma(gray), 0.0)
    rotation = _safe(lambda: _rotation_angle(gray), 0.0)
    skew = _safe(lambda: _skew_angle(gray), 0.0)
    megapixels = round((w * h) / 1_000_000.0, 2)

    # ---- map raw metrics -> 0..100 sub-scores -----------------------------
    # Combine the two focus measures (Laplacian variance + Tenengrad) for a
    # robust "sharpness" sub-score that is less sensitive to a single estimator.
    blur_s = _ramp(blur, 20.0, 250.0)
    teng_s = _ramp(sharpness, 200.0, 3000.0)
    sub = {
        "sharpness": round(0.6 * blur_s + 0.4 * teng_s, 1),
        "brightness": round(_window(brightness, 30, 95, 180, 235), 1),
        "contrast": round(_ramp(contrast, 20.0, 65.0), 1),
        # Lower sigma is better — invert. ~3 is clean, ~18 is very noisy.
        "noise": round(100.0 - _ramp(noise, 3.0, 18.0), 1),
        "resolution": round(_ramp(megapixels, 0.3, 2.0), 1),
        "geometry": round(
            100.0 - _ramp(abs(rotation), 2.0, 30.0) * 0.6 - _ramp(abs(skew), 1.0, 15.0) * 0.4,
            1,
        ),
    }

    overall = round(sum(sub[k] * _WEIGHTS[k] for k in _WEIGHTS), 1)
    passed = overall >= threshold

    metrics = {
        "blur_score": round(blur, 1),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
        "sharpness": round(sharpness, 1),
        "noise_level": round(noise, 2),
        "width": int(w),
        "height": int(h),
        "megapixels": megapixels,
        "rotation_angle": round(rotation, 2),
        "skew_angle": round(skew, 2),
    }

    recommendations = _recommendations(sub, metrics, brightness)
    if not passed:
        warnings.insert(
            0,
            f"Image quality is low ({overall:.0f}%). OCR accuracy may suffer — "
            "consider recapturing the prescription before continuing.",
        )

    return QualityReport(
        overall_score=overall,
        rating=_rating(overall),
        passed=passed,
        threshold=threshold,
        metrics=metrics,
        subscores=sub,
        recommendations=recommendations,
        warnings=warnings,
    )
