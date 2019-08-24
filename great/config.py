from appdirs import user_config_dir
from filesystems import Path, native
import toml


_PATH = Path.from_string(user_config_dir(__package__)).descendant(
    "config.toml",
)


def load(path=_PATH, fs=native.FS()):
    return toml.loads(fs.get_contents(path))
