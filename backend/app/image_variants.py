from pathlib import Path

from PIL import Image

VARIANT_SPECS: dict[str, int] = {
    "thumbnail": 320,
    "preview": 1280,
}


def build_variant_path(original_path: Path, variant: str) -> Path:
    suffix = original_path.suffix or ".png"
    return original_path.with_name(f"{original_path.stem}__{variant}{suffix}")


def ensure_image_variants(original_path: Path) -> dict[str, str]:
    if not original_path.exists():
        return {}

    variants: dict[str, str] = {}
    try:
        with Image.open(original_path) as image:
            for variant, target_width in VARIANT_SPECS.items():
                if image.width <= target_width:
                    continue
                ratio = target_width / max(1, image.width)
                target_height = max(1, int(image.height * ratio))
                resized = image.copy()
                resized.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
                variant_path = build_variant_path(original_path, variant)
                save_format = image.format or "PNG"
                resized.save(variant_path, format=save_format)
                variants[f"{variant}_path"] = str(variant_path)
    except Exception:  # noqa: BLE001
        return {}

    return variants
