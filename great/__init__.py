try:
    from importlib import metadata
except ImportError: # for Python<3.8
    import importlib_metadata as metadata


_great = metadata.metadata("great")
__version__ = _great["Version"]
__url__ = _great["Home-page"]
