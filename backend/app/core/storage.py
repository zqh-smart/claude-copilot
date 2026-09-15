from pathlib import Path


class LocalFileStorage:
    def ensure_dir(self, path: str | Path) -> Path:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_bytes(self, directory: str | Path, filename: str, data: bytes) -> Path:
        target_dir = self.ensure_dir(directory)
        target = target_dir / filename
        target.write_bytes(data)
        return target

    def save_text(self, path: str | Path, content: str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_bytes(self, path: str | Path) -> bytes:
        return Path(path).read_bytes()
