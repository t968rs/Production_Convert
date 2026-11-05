"""Shared pytest configuration for the tests package.

The sibling ``__init__.py`` makes ``tests`` a package, so pytest's default import mode inserts the repository root
(the first directory above the package) into ``sys.path`` and the tests can import ``conversion``.
"""
