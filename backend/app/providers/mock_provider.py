import random
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import settings
from ..models import Task
from .base import BaseProvider


def _make_fake_png(path: Path, label: str) -> None:
    image = Image.new(
        "RGB",
        (512, 512),
        color=(random.randint(20, 235), random.randint(20, 235), random.randint(20, 235)),
    )
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), label, fill=(255, 255, 255))
    image.save(path, format="PNG")


class MockProvider(BaseProvider):
    def generate(self, task: Task) -> list[dict]:
        out_dir = settings.data_dir / "outputs" / task.id
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[dict] = []
        for i in range(task.n_outputs):
            index = i + 1
            output_path = out_dir / f"output_{index}.png"
            _make_fake_png(output_path, f"task={task.id}\nidx={index}")

            outputs.append(
                {
                    "file_path": str(output_path),
                    "mime_type": "image/png",
                    "file_type": "image",
                    "file_name": output_path.name,
                    "file_size": output_path.stat().st_size,
                    "index": index,
                }
            )

        return outputs
