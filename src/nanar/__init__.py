"""Nanar: a video player for the PC plugged into the TV, driven from a phone."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nanar")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0"
