from pathlib import Path
import pytest
from xingcheng.ocr import decode
ROOT=Path(__file__).parent/"fixtures/ocr"

def test_image_resource_limits_before_decode():
    from PIL import Image
    import io

    b = io.BytesIO()
    Image.new("RGB", (4001, 3000)).save(b, format="PNG")
    with pytest.raises(ValueError, match="1200"):
        decode(b.getvalue(), {})
    with pytest.raises(ValueError):
        decode(b"broken", {})
    with pytest.raises(ValueError):
        decode((ROOT / "clean.png").read_bytes(), {"crop": [0.7, 0, 0.2, 1]})
