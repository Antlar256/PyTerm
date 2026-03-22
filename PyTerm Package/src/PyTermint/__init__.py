# pyterm/__init__.py
"""
This is a terminal engine which is desined to be imported by other python files to use its features.
init(screen); return arr, {vars_dict}, "optional command string"
tick(screen, vars, keys): return None

"""

from .PyTerm import *
__version__ = "0.0.1"

__all__ = [name for name, obj in globals().items() 
           if not name.startswith('_') 
           and getattr(obj, '__module__', '').startswith('PyTerm')]