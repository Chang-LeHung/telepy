import sys

from setuptools import Extension, find_packages, setup  # type: ignore

ext_modules = [
    Extension(
        name="telepy._telepysys",
        sources=["src/telepy/telepysys/telepysys.c"],
        include_dirs=["src/telepy/telepysys"],
        extra_compile_args={"win32": []}.get(sys.platform, ["-Werror", "-std=c11"]),
        extra_link_args={"win32": []}.get(sys.platform, ["-lpthread"]),
    )
]

setup(
    name="telepy",
    version="0.1.0",
    description="A Python diagnostic tool.",
    author="changlehung",
    author_email="changlehung@gmail.com",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    ext_modules=ext_modules,
)
