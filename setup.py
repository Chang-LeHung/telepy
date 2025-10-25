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
            # On Windows, let setuptools handle the compilation via MSVC
            # We need to compile tree.cc first as a separate step
            from distutils.ccompiler import new_compiler
            from distutils.sysconfig import customize_compiler

            compiler = new_compiler(compiler=None)
            customize_compiler(compiler)

            # Set C++ standard for MSVC
            if hasattr(compiler, "compiler_type") and compiler.compiler_type == "msvc":
                # Add C++14 standard flag for MSVC
                extra_args = ["/std:c++14", "/EHsc"] + [
                    f for f in flags if f not in ["/EHsc", "/std:c++14"]
                ]
            else:
                extra_args = flags

            # Compile tree.cc
            objects = compiler.compile(
                ["src/telepy/telepysys/tree.cc"],
                output_dir="build/temp",
                extra_postargs=extra_args,
            )
            # Store the compiled object path for linking
            self.tree_objects = objects
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
            self.tree_objects = ["build/tree.o"]
        super().run()

    def build_extensions(self):
        # Add tree object files to the telexsys extension
        if hasattr(self, "tree_objects"):
            for ext in self.extensions:
                if ext.name == "telepy._telexsys":
                    if IS_WINDOWS:
                        # On Windows, add as extra objects
                        if not hasattr(ext, "extra_objects"):
                            ext.extra_objects = []
                        ext.extra_objects.extend(self.tree_objects)
                    else:
                        # On Unix, add as extra link args
                        ext.extra_link_args.extend(self.tree_objects)
        super().build_extensions()


ext_modules = [
    Extension(
        name="telepy._telexsys",
        sources=[
            "src/telepy/telexsys/telexsys.c",
            "src/telepy/telexsys/inject.c",
        ],
        include_dirs=["src/telepy/telexsys"],
        extra_compile_args=flags,
        language="c++",
    ),
    Extension(
        name="telepy._gc_stats",
        sources=["src/telepy/telexsys/gc_stats.c"],
        include_dirs=["src/telepy/telexsys"],
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
