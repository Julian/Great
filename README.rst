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
    great init                                       # seeds one list per kind
    great want "Severance" --kind tv                 # queue what you haven't watched
    great consumed "The Godfather" --kind movie      # catalog + diary + focused rank
    great consumed "Severance"                       # promotes the wanted item in
    great rank movies                                # broader ranking pass when you want
    great rank tv --want                             # rank watch-next priorities
    great build                                      # render → dist/

A working sample lives in ``examples/sample-data/``.
``great init`` (default ``--with-pages``) drops a GitHub Actions workflow that builds the site and deploys to Pages on every push.


CLI
---

``great init [PATH] [--list NAME:KIND]... [--with-pages]``
    Bootstrap a data repo (drops a Pages-deploy workflow by default).

``great lists``
    Show configured lists.

``great rank <list>`` / ``great rank <kind> --want``
    Run a Textual ranking session — over a favorite-list, or (with
    ``--want``) the want queue for ``<kind>``.

``great show <list>`` / ``great show <kind> --want``
    Print the inferred ranking, favorites or want.

``great consumed <item> [--kind KIND] [--at DATE] [--notes ...] [--no-log] [--no-rank]``
    Mark an item as consumed. Catalogs it if new (``--kind`` required
    for brand-new titles), promotes it from the want queue if wanted,
    writes a diary entry, and runs a focused ranking session for
    newly-cataloged items. ``--no-log`` skips the diary;
    ``--no-rank`` skips ranking. Already-cataloged items get a
    diary row only — use ``great rank`` to re-rank them.

``great started <item> [--kind KIND] [--at DATE] [--notes ...]``
    Log that you've started an item; catalog it if new. Never promotes
    from the want queue or ranks (no opinion formed yet).

``great abandoned <item> [--kind KIND] [--at DATE] [--notes ...]``
    Log that you've abandoned an item; catalog it if new. Never
    promotes or ranks.

``great log <item> [--status ...] [--notes ...] [--at DATE]``
    Low-level diary append for items already in the catalog or want
    queue. Useful for backfilling; never auto-creates, never ranks.

``great want <title> --kind KIND [--year YEAR] [--id ID]``
    Add a free-form title to the kind's want queue (one queue per kind).

``great unwant <item> [--kind KIND]``
    Remove from the kind's want queue.

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
