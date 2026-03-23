"""EXIF GPS extraction — pull location coordinates from image metadata.

Supports: JPEG, TIFF, PNG (if EXIF present), WebP
Works with: local files, URLs, base64 data
No API keys or ML models needed.
"""

import io
import logging
from typing import Any

import httpx
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)


def _get_exif_data(image: Image.Image) -> dict:
    """Extract all EXIF data from a PIL Image."""
    exif_data = {}
    info = image._getexif()
    if not info:
        return exif_data
    for tag_id, value in info.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "GPSInfo":
            gps = {}
            for gps_tag_id, gps_value in value.items():
                gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                gps[gps_tag] = gps_value
            exif_data["GPSInfo"] = gps
        else:
            exif_data[tag] = value
    return exif_data


def _gps_to_decimal(gps_coords, ref) -> float:
    """Convert GPS coordinates from DMS (degrees, minutes, seconds) to decimal."""
    try:
        degrees = float(gps_coords[0])
        minutes = float(gps_coords[1])
        seconds = float(gps_coords[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, IndexError):
        return None


def extract_gps_from_image(image: Image.Image) -> dict:
    """Extract GPS coordinates and metadata from image EXIF data."""
    exif = _get_exif_data(image)
    gps_info = exif.get("GPSInfo", {})

    if not gps_info:
        return {"has_gps": False}

    lat = _gps_to_decimal(
        gps_info.get("GPSLatitude"),
        gps_info.get("GPSLatitudeRef", "N"),
    )
    lon = _gps_to_decimal(
        gps_info.get("GPSLongitude"),
        gps_info.get("GPSLongitudeRef", "E"),
    )

    if lat is None or lon is None:
        return {"has_gps": False}

    result = {
        "has_gps": True,
        "lat": lat,
        "lon": lon,
    }

    # Optional GPS metadata
    if "GPSAltitude" in gps_info:
        try:
            alt = float(gps_info["GPSAltitude"])
            ref = gps_info.get("GPSAltitudeRef", 0)
            if ref == 1:
                alt = -alt
            result["altitude_m"] = round(alt, 1)
        except (TypeError, ValueError):
            pass

    if "GPSSpeed" in gps_info:
        try:
            result["speed"] = float(gps_info["GPSSpeed"])
            result["speed_ref"] = gps_info.get("GPSSpeedRef", "K")
        except (TypeError, ValueError):
            pass

    if "GPSImgDirection" in gps_info:
        try:
            result["direction"] = float(gps_info["GPSImgDirection"])
        except (TypeError, ValueError):
            pass

    if "GPSTimeStamp" in gps_info:
        try:
            ts = gps_info["GPSTimeStamp"]
            result["gps_time"] = f"{int(ts[0]):02d}:{int(ts[1]):02d}:{int(ts[2]):02d}"
        except (TypeError, ValueError, IndexError):
            pass

    if "GPSDateStamp" in gps_info:
        result["gps_date"] = str(gps_info["GPSDateStamp"])

    # Non-GPS EXIF metadata
    if "Make" in exif:
        result["camera_make"] = str(exif["Make"]).strip()
    if "Model" in exif:
        result["camera_model"] = str(exif["Model"]).strip()
    if "DateTime" in exif:
        result["datetime"] = str(exif["DateTime"])
    if "Software" in exif:
        result["software"] = str(exif["Software"]).strip()

    return result


class ExifExtractorRunner(BaseToolRunner):
    tool_name = "exif_extractor"
    cache_ttl = 300

    async def extract_from_url(self, url: str) -> dict:
        """Download image from URL and extract GPS + EXIF metadata."""
        cache_key = self._cache_key("url", url)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "ShadowLens/1.0"})
                if resp.status_code != 200:
                    return {"status": "error", "error": f"HTTP {resp.status_code}", "url": url}

                content_type = resp.headers.get("content-type", "")
                if not any(t in content_type for t in ["image", "octet-stream"]):
                    return {"status": "error", "error": f"Not an image: {content_type}", "url": url}

                image = Image.open(io.BytesIO(resp.content))
                gps_data = extract_gps_from_image(image)

                output = {
                    "status": "ok",
                    "url": url,
                    "format": image.format,
                    "size": f"{image.width}x{image.height}",
                    **gps_data,
                    "source": "exif",
                }
        except Exception as e:
            logger.warning(f"EXIF extraction failed for {url}: {e}")
            output = {"status": "error", "error": str(e), "url": url}

        self._set_cached(cache_key, output)
        return output
