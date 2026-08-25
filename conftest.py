"""Put the repository root on sys.path so tests can ``import src.*`` without an
install step. Kept at the root deliberately: pytest prepends the directory of
the rootdir conftest, which is exactly what the flat ``src/`` layout needs.
"""
