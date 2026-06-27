"""Root conftest.

Ensures the repository root is on sys.path so tests can import the project
as `src.core...` (PEP 420 namespace packages) regardless of the working
directory pytest is invoked from.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
