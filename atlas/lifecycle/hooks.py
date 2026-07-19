"""
Atlas Lifecycle Hooks

Base interface for components that participate
in the Atlas lifecycle.
"""


class LifecycleHooks:
    """
    Base lifecycle hook implementation.
    """

    def before_initialize(self):
        pass

    def after_initialize(self):
        pass

    def before_start(self):
        pass

    def after_start(self):
        pass

    def before_stop(self):
        pass

    def after_stop(self):
        pass