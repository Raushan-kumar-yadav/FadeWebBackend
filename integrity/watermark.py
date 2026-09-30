import logging
from collections import Counter

logger = logging.getLogger(__name__)
WM_BITS   = 32
WM_METHOD = "dwtDct"
EXTRACT_SAMPLES  = 12
MIN_CONFIDENCE   = 0.30

try:
    import cv2 as _cv2
    from imwatermark import WatermarkDecoder as _Dec
    _WM_OK = True
except ImportError:
    _WM_OK = False
    logger.warning("invisible-watermark not installed: pip install invisible-watermark")

def extract_watermark_video(path: str) -> str | None:
    if not _WM_OK:
        return None
    try:
        cap = _cv2.VideoCapture(path)
        total = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            cap.release(); return None
        margin  = max(1, total // 50)
        indices = [margin + int(i * (total - 2*margin) / (EXTRACT_SAMPLES-1)) for i in range(EXTRACT_SAMPLES)]
        dec = _Dec("bytes", WM_BITS)
        votes = []
        for idx in indices:
            cap.set(_cv2.CAP_PROP_POS_FRAMES, float(idx))
            ret, frame = cap.read()
            if not ret: continue
            try:
                wm = dec.decode(frame, WM_METHOD)
                if wm and len(wm) == 4:
                    votes.append(wm.hex())
            except Exception:
                pass
        cap.release()
        if not votes: return None
        winner, count = Counter(votes).most_common(1)[0]
        return winner if count / len(votes) >= MIN_CONFIDENCE else None
    except Exception as e:
        logger.warning("extract_watermark_video failed: %s", e)
        return None

def extract_watermark_image(path: str) -> str | None:
    if not _WM_OK:
        return None
    try:
        import cv2
        from imwatermark import WatermarkDecoder
        frame = cv2.imread(path)
        if frame is None: return None
        dec = WatermarkDecoder("bytes", WM_BITS)
        wm  = dec.decode(frame, WM_METHOD)
        return wm.hex() if wm and len(wm) == 4 else None
    except Exception as e:
        logger.warning("extract_watermark_image failed: %s", e)
        return None

def extract_watermark(path: str, kind: str) -> str | None:
    if kind == "video":
        return extract_watermark_video(path)
    if kind == "image":
        return extract_watermark_image(path)
    return None  # PDF: no watermark
