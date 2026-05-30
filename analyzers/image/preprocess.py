"""Downscale food photos before they reach the vision model.

gpt-5.4 tokenizes an image as 32px x 32px patches, so its token cost scales with
pixel AREA and is not floored by an internal upscale (unlike the older 512px-tile
models, which forced the shortest side to 768px and made client-side resizing
pointless). Capping the longest side therefore trims the per-photo token bill in
rough proportion to the area removed: a typical ~1280px Telegram photo drops by
about a third at 1024px while keeping ample detail for portion estimation.

Resizing only ever shrinks. Images already within the cap, and bytes Pillow
cannot decode, pass through untouched so a preprocessing hiccup never blocks an
analysis.
"""

import io
import logging

logger = logging.getLogger(__name__)

# Longest-side cap, in pixels. 1024px is the conservative sweet spot: clearly
# cheaper than Telegram's ~1280px without visibly costing food/portion detail.
DEFAULT_MAX_DIM = 1024
_JPEG_QUALITY = 85


def downscale_image(
    image_bytes: bytes,
    media_type: str,
    *,
    max_dim: int = DEFAULT_MAX_DIM,
) -> tuple[bytes, str]:
    """Return (bytes, media_type) with the longest side capped at ``max_dim``.

    Best-effort: any failure (Pillow missing, unknown format, decode error)
    returns the original bytes and media type so the analysis still runs.
    """
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - Pillow should be installed
        logger.warning("Pillow unavailable; sending image without downscale")
        return image_bytes, media_type

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if max(image.size) <= max_dim:
                return image_bytes, media_type  # already small enough

            original_size = image.size
            image.thumbnail((max_dim, max_dim))  # in place, preserves aspect ratio
            # JPEG holds neither alpha nor palette; flatten anything else to RGB.
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    except Exception:
        logger.exception("image downscale failed; sending original bytes")
        return image_bytes, media_type

    resized = buffer.getvalue()
    logger.info(
        "downscaled image %s -> %s (%s -> %s bytes)",
        original_size,
        image.size,
        len(image_bytes),
        len(resized),
    )
    return resized, "image/jpeg"
