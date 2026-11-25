"""AutoML uploads one zip; the downloader wraps it again. predictor.pkl must still be found."""
import io
import zipfile
from pathlib import Path

from app.services.model_archive import unpack_model_archives


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_nested_automl_predictor_zip_is_unpacked(tmp_path: Path):
    inner = _zip_bytes({"predictor.pkl": b"not-a-real-predictor"})
    outer = _zip_bytes({"automl_predictor.zip": inner})
    with zipfile.ZipFile(io.BytesIO(outer)) as archive:
        archive.extractall(tmp_path)

    unpack_model_archives(tmp_path)

    found = list(tmp_path.rglob("predictor.pkl"))
    assert len(found) == 1
    assert found[0].read_bytes() == b"not-a-real-predictor"
