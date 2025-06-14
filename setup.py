import os
import subprocess

from setuptools import Extension, find_packages, setup  # type: ignore
from setuptools.command.build_ext import build_ext  # type: ignore

os.makedirs("build", exist_ok=True)


def prepare_flags():
    flags = os.environ.get("TELEPY_FLAGS", "").split(" ")
    if "-g" not in flags:
        flags.append("-O2")

    if "-Werror" not in flags:
        flags.append("-Werror")

    if "-Wextra" not in flags:
        flags.append("-Wextra")

    if "-Wall" not in flags:
        flags.append("-Wall")
    return flags


flags = prepare_flags()


class Builder(build_ext):
    def run(self):
        cmd = [
            "g++",
            "-c",
            "-std=c++11",
            "src/telepy/telepysys/tree.cc",
            *(flags),
            "-o",
            "build/tree.o",
            *flags,
        ]
        subprocess.check_call(cmd)
        super().run()


ext_modules = [
    Extension(
        name="telepy._telepysys",
        sources=[
            "src/telepy/telepysys/telepysys.c",
            "src/telepy/telepysys/inject.c",
        ],
        include_dirs=["src/telepy/telepysys"],
        extra_compile_args=flags,
        extra_link_args=["build/tree.o"],
        language="c++",
    )
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
