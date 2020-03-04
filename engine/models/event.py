# Based on https://stackoverflow.com/questions/1092531/event-system-in-python/1096614#1096614
import logging

logger = logging.getLogger('youps')  # type: logging.Logger

class Event:
    """Simple wrapper for a events

    Usage:
        > class MockFileWatcher:
        >     def __init__(self):
        >         self.fileChanged = Event()
        >     def watchFiles(self):
        >         source_path = "foo"
        >         self.fileChanged(source_path)
        > def log_file_change(source_path):
        >     print "%r changed." % (source_path,)
        > def log_file_change2(source_path):
        >     print "%r changed!" % (source_path,)
        > watcher              = MockFileWatcher()
        > watcher.fileChanged += log_file_change2
        > watcher.fileChanged += log_file_change
        > watcher.fileChanged -= log_file_change2
        > watcher.watchFiles()
    """

    def __init__(self, env=None):
        self.handlers = set()
        self.env = env

    def handle(self, handler):
        self.handlers.add(handler)
        return self

    def unhandle(self, handler):
        try:
            self.handlers.remove(handler)
        except Exception:
            raise ValueError("Handler is not handling this event, so cannot unhandle it.")
        return self

    def fire(self, *args, **kwargs):
        for handler in self.handlers:
            exec(handler(*args, **kwargs), self.env)
            

    def removeAllHandles(self):
        self.handlers = set()

    def getHandlerCount(self):
        return len(self.handlers)

    def __iadd__(self, handler):
        self.handle(handler)
        return self

    def __isub__(self, handler):
        self.unhandle(handler)
        return self

    def __call__(self, *args, **kwargs):
        self.fire(*args, **kwargs)

    def __len__(self):
        return self.getHandlerCount()
