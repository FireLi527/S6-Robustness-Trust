"""Smoke-test the Linux/WSL GPU training environment without downloading weights."""

from __future__ import annotations

import json
import platform
import time
from importlib.metadata import version
from pathlib import Path

import torch
import torchvision
from PIL import Image
from torchvision.models import resnet18


PROJECT_ROOT = Path(__file__).resolve().parents[2]
from dataset_config import IMAGE_ROOT

def sample_image_path():
    return next((IMAGE_ROOT / "classification" / "train").rglob("*.png"))


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available in this Python environment")

    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    free_bytes, total_bytes = torch.cuda.mem_get_info(device)

    SAMPLE_IMAGE = sample_image_path()
    with Image.open(SAMPLE_IMAGE) as image:
        sample_image = {
            "path": str(SAMPLE_IMAGE),
            "mode": image.mode,
            "size": list(image.size),
        }

    torch.manual_seed(2026)
    model = resnet18(weights=None, num_classes=10).to(device).eval()
    inputs = torch.randn(8, 3, 224, 224, device=device)

    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.float16):
        output = model(inputs)
    torch.cuda.synchronize()
    elapsed_ms = (time.perf_counter() - started) * 1000

    summary = {
        "status": "PASS",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "training_packages": {
            package: version(package)
            for package in (
                "numpy",
                "pandas",
                "scikit-learn",
                "matplotlib",
                "seaborn",
                "tensorboard",
                "open-clip-torch",
            )
        },
        "cuda_runtime": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
        "gpu": properties.name,
        "compute_capability": f"{properties.major}.{properties.minor}",
        "supported_architectures": torch.cuda.get_arch_list(),
        "gpu_memory_total_gib": round(total_bytes / 1024**3, 2),
        "gpu_memory_free_before_test_gib": round(free_bytes / 1024**3, 2),
        "resnet18_batch": 8,
        "resnet18_output_shape": list(output.shape),
        "resnet18_forward_ms": round(elapsed_ms, 2),
        "sample_image": sample_image,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
