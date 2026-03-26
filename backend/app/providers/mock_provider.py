import random
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import settings
from ..models import Task
from ..provider_params import normalize_task_params
from .base import BaseProvider
from .types import ProviderResultItem


def _make_fake_png(path: Path, label: str, width: int, height: int) -> None:
    image = Image.new(
        "RGB",
        (width, height),
        color=(random.randint(20, 235), random.randint(20, 235), random.randint(20, 235)),
    )
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), label, fill=(255, 255, 255))
    image.save(path, format="PNG")


class MockProvider(BaseProvider):
    name = "mock"
    supports_image = True
    supports_video = False

    def generate(
        self,
        task: Task,
        on_output: Callable[[ProviderResultItem], None] | None = None,
    ) -> list[ProviderResultItem]:
        params = normalize_task_params(task)

        out_dir = settings.outputs_dir / task.id
        out_dir.mkdir(parents=True, exist_ok=True)

        width = params.width or 512
        height = params.height or 512

        outputs: list[ProviderResultItem] = []
        for i in range(task.n_outputs):
            index = i + 1
            output_path = out_dir / f"output_{index}.png"
            label = f"task={task.id}\nidx={index}"
            if params.model_dump(exclude_none=True):
                label = f"{label}\nparams={params.model_dump(exclude_none=True)}"
            _make_fake_png(output_path, label, width, height)

            output_item = ProviderResultItem(
                index=index,
                file_path=str(output_path),
                mime_type="image/png",
                file_type="image",
                file_name=output_path.name,
                file_size=output_path.stat().st_size,
                width=width,
                height=height,
            )
            outputs.append(output_item)
            if on_output:
                on_output(output_item)

        return outputs
