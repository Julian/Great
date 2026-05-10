"""
Build hook that materialises the GitHub Pages workflow shipped with great.

At build time we resolve the four pinned actions (checkout, setup-uv,
upload-pages-artifact, deploy-pages) to their current commit SHAs via the
GitHub API and render the workflow template into ``great/_data/``. If
GitHub is unreachable, the previously committed copy is kept — released
artifacts may then ship slightly stale pins, but the build never breaks
on a transient outage.
"""

from pathlib import Path
import sys
import urllib.request

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
import jinja2

PINS = {
    "checkout": ("actions", "checkout", "v6"),
    "setup_uv": ("astral-sh", "setup-uv", "v7"),
    "upload_pages_artifact": ("actions", "upload-pages-artifact", "v3"),
    "deploy_pages": ("actions", "deploy-pages", "v4"),
}

ROOT = Path(__file__).parent
DATA = ROOT / "great" / "_data"
TEMPLATE_NAME = "pages_workflow.yml.template"
OUTPUT = DATA / "pages_workflow.yml"
TIMEOUT = 10.0


def _resolve_sha(owner: str, repo: str, ref: str) -> str:
    """Return the commit SHA that ``owner/repo@ref`` resolves to."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"Accept": "application/vnd.github.sha"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
        return resp.read().decode("ascii").strip()


def _render(context: dict[str, str]) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(DATA),
        variable_start_string="<<",
        variable_end_string=">>",
        autoescape=False,  # noqa: S701  (rendering YAML, not HTML)
        keep_trailing_newline=True,
    )
    return env.get_template(TEMPLATE_NAME).render(context)


def refresh() -> bool:
    """Rebuild ``pages_workflow.yml`` from live SHAs. Return success."""
    context: dict[str, str] = {}
    try:
        for key, (owner, repo, version) in PINS.items():
            context[f"{key}_sha"] = _resolve_sha(owner, repo, version)
            context[f"{key}_version"] = version
    except OSError as e:
        sys.stderr.write(
            f"warning: unable to resolve action SHAs ({e}); "
            f"keeping {OUTPUT.name} as-is.\n",
        )
        return False
    OUTPUT.write_text(_render(context), encoding="utf-8")
    return True


class PagesWorkflowHook(BuildHookInterface):
    """Materialise ``pages_workflow.yml`` before files are collected."""

    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):  # noqa: D102
        # Only refresh for sdist builds. Wheels published to PyPI are
        # built from the sdist (which already carries the freshly
        # resolved file), and skipping wheel/editable builds avoids
        # surprising contributors with phantom working-tree changes
        # after `uv sync` or `pip install -e .`.
        if self.target_name != "sdist":
            return
        refresh()


if __name__ == "__main__":
    sys.exit(0 if refresh() else 1)
