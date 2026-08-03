"""Setup script for the Track Alignment tool."""
from setuptools import setup, find_packages

setup(
    name="track_alignment",
    version="1.0.0",
    description="Interactive MagneMotion track waypoint editor",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["PySide6>=6.5"],
)
