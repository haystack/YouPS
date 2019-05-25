from __future__ import print_function
import typing as t

import logging


def _get_class_name(obj):
    # type: (object) -> str
    """Get the class name from an object

    Returns:
        str: the name of the class which represents the object
    """
    return obj.__class__.__name__


def _get_method_name(prop):
    # type: (t.Callable) -> str
    """Get the name of a method

    Args:
        prop (t.Callable): a method on an object

    Returns:
        str: the name which represents the method
    """
    return prop.__name__


def _get_logger():
    # type: () -> logging.Logger
    return logging.getLogger('youps')


def _log_info(obj, info):
    # type: (t.AnyStr) -> None
    assert obj._imap_client is not None
    if hasattr(obj._imap_client, 'user_property_log') and \
            obj._imap_client.user_property_log is not None and \
            hasattr(obj._imap_client, "nested_log") and \
            obj._imap_client.nested_log is False:
        _get_logger().critical("HEEEEEEEEEEERE")
        user_property_log = obj._imap_client.user_property_log
        user_property_log.write(info)
        user_property_log.write(u"\n")


def _set_in_log(obj, value):
    # if hasattr(obj._imap_client, 'user_property_log') and obj._imap_client.user_property_log is not None:
    obj._imap_client.nested_log = value

def _is_nested(obj):
    # if hasattr(obj._imap_client, 'user_property_log') and obj._imap_client.user_property_log is not None:
    if hasattr(obj._imap_client, 'nested_log'):
        return obj._imap_client.nested_log
    return False

class CustomProperty(object):
    "Emulate PyProperty_Type() in Objects/descrobject.c"

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        if doc is None and fget is not None:
            doc = fget.__doc__
        self.__doc__ = doc

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")

        if _is_nested(obj):
            return self.fget(obj)

        _set_in_log(obj, True)

        # value we are getting or wrapping around
        value = self.fget(obj)

        # name of the class we are a property on
        class_name = _get_class_name(obj)
        # name of the property we're wrapping around
        property_name = _get_method_name(self.fget)

        info_string = u"get {c}.{p}\t{v}".format(
            c=class_name, p=property_name, v=value)
        _set_in_log(obj, False)

        if not property_name.startswith("_"):
            _log_info(obj, info_string)

        return value

    def __set__(self, obj, new_value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        if _is_nested(obj):
            self.fset(obj, new_value)
            return
        # TODO doesn't really make sense normally but we want to fget for logging
        if self.fget is None:
            raise AttributeError("unreadable attribute")

        _set_in_log(obj, True)
        curr_value = self.fget(obj)
        class_name = _get_class_name(obj)
        property_name = _get_method_name(self.fset)
        info_string = u"set {c}.{p}\t{v} -> {nv}".format(
            c=class_name, p=property_name, v=curr_value, nv=new_value)
        self.fset(obj, new_value)
        _set_in_log(obj, False)

        if not property_name.startswith("_"):
            _log_info(obj, info_string)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__)
