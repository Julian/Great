=========
``Great``
=========

|CI|

.. |CI| image:: https://github.com/Julian/Great/workflows/CI/badge.svg
  :alt: Build status
  :target: https://github.com/Julian/Great/actions?query=workflow%3ACI

A reusable engine for personal media tracking and ranking, inspired by `gwern.net/resorter <https://gwern.net/resorter>`_.
Rather than asking you to assign absolute scores, ``Great`` elicits pairwise or k-way comparisons and infers rankings via the Plackett-Luce model.

The work is split across two repositories.
This one is the engine: CLI, library, and static-site renderer.
A separate data repo holds your items, comparisons, and consumption log as plain text files in git, and deploys a public ranked-list site to GitHub Pages on push.


Install
-------

.. code-block:: sh

    uv tool install great


Quick Start
-----------

Bootstrap a data repo and try the loop locally:

.. code-block:: sh

    mkdir my-media && cd my-media
    great init --list movies:movie --list tv:tv
    # Edit items/movie.toml to add some items, then:
    great rank movies          # interactive Textual session
    great consumed "Anora"     # log it (auto-removes from any want queue)
    great want "Severance"     # add to want queue
    great build                # render → dist/

A working sample lives in ``examples/sample-data/``.
``great init`` (default ``--with-pages``) drops a GitHub Actions workflow that builds the site and deploys to Pages on every push.


CLI
---

``great init [PATH] [--list NAME:KIND]... [--with-pages]``
    Bootstrap a data repo (drops a Pages-deploy workflow by default).

``great lists``
    Show configured lists.

``great rank <list>``
    Run a Textual ranking session.

``great show <list>``
    Print the inferred ranking.

``great log <item> [--status ...] [--notes ...] [--at DATE]``
    Append a diary entry.

``great consumed <item> [--at DATE]``
    Alias for ``log --status consumed``.

``great want <item> [--list ...] [--priority ...]``
    Add to a want queue.

``great unwant <item>``
    Remove from want queues.

``great build [--out dist/]``
    Render the static site.


Development
-----------

.. code-block:: sh

    uv sync
    uvx nox            # runs all default sessions
    uvx nox -s tests   # just tests
    uvx nox -s style   # ruff check + format
    uvx nox -s typing  # ty
