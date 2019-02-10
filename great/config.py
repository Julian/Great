from appdirs import user_config_dir
from filesystems import Path, native
import pytoml


_PATH = Path.from_string(user_config_dir(__package__)).descendant(
    "config.toml",
)


def load(path=_PATH, fs=native.FS()):
    return pytoml.loads(fs.get_contents(path))
