# Store utilities for use in the engine for some future where the engine
# can potentially exist by itself
from itertools import izip
import typing as t  # noqa: F401 ignore unused we use it for typing

def grouper(iterable, n):
    """Group data from an iterable into chunks of size n

    The last chunk can be of size 1 to n
    
    Args:
        iterable (t.Iterable): iterable object
        n (int): chunk size
    
    Returns:
        t.Iterable: iterable containing n elements
    """
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return izip(*args)