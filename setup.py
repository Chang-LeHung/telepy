import os
import platform
import subprocess
import sys

from setuptools import Extension, find_packages, setup  # type: ignore
from setuptools.command.build_ext import build_ext  # type: ignore

os.makedirs("build", exist_ok=True)

# Detect platform
IS_WINDOWS = sys.platform == "win32" or platform.system() == "Windows"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def prepare_flags():
    """Prepare compiler flags based on platform"""
    if IS_WINDOWS:
        # MSVC flags
        flags = os.environ.get("TELEPY_FLAGS", "").split(" ")
        # Add Windows-specific flags if not present
        default_flags = ["/W4", "/EHsc", "/O2"]
        for flag in default_flags:
            if flag not in flags:
                flags.append(flag)
        return [f for f in flags if f != ""]
    else:
        # GCC/Clang flags for Unix-like systems
        flags = os.environ.get("TELEPY_FLAGS", "").split(" ")
        if "-g" not in flags:
            flags.append("-O2")

        if "-Werror" not in flags:
            flags.append("-Werror")

        if "-Wextra" not in flags:
            flags.append("-Wextra")

        if "-Wall" not in flags:
            flags.append("-Wall")
        return [f for f in flags if f != ""]


flags = prepare_flags()


class Builder(build_ext):
    def run(self):
        if IS_WINDOWS:
            # Use MSVC on Windows
            cmd = [
                "cl",
                "/c",
                "/std:c++14",
                "/EHsc",
                "src/telepy/telepysys/tree.cc",
                "/Fo:build/tree.obj",
                *[f for f in flags if f not in ["/EHsc", "/std:c++14"]],
            ]
            try:
                subprocess.check_call(cmd)
            except FileNotFoundError:
                print(
                    "Warning: MSVC compiler (cl) not found. "
                    "Make sure Visual Studio or Build Tools are installed.",
                    file=sys.stderr,
                )
                raise
        else:
            # Use g++ on Unix-like systems
            cmd = [
                "g++",
                "-c",
                "-std=c++11",
                "-fPIC",
                "src/telepy/telepysys/tree.cc",
                "-pthread",
                "-o",
                "build/tree.o",
                *flags,
            ]
            subprocess.check_call(cmd)
        super().run()


# Determine the tree object file based on platform
tree_obj = "build/tree.obj" if IS_WINDOWS else "build/tree.o"

ext_modules = [
    Extension(
        name="telepy._telepysys",
        sources=[
            "src/telepy/telepysys/telepysys.c",
            "src/telepy/telepysys/inject.c",
        ],
        include_dirs=["src/telepy/telepysys"],
        extra_compile_args=flags,
        extra_link_args=[tree_obj],
        language="c++",
    ),
    Extension(
        name="telepy._gc_stats",
        sources=["src/telepy/telepysys/gc_stats.c"],
        include_dirs=["src/telepy/telepysys"],
        extra_compile_args=flags,
        language="c",
    ),
]

setup(
    name="telepy",
    description="A Python diagnostic tool.",
    author="changlehung",
    author_email="changlehung@gmail.com",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    ext_modules=ext_modules,
    cmdclass={"build_ext": Builder},
)
