"""
A CLI to a Great server.
"""

import click

from great import __version__


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(version=__version__, prog_name="great")
def main():
    pass
