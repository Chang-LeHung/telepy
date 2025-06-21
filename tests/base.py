import inspect
import logging
from unittest import TestCase

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class TestBase(TestCase):
    @staticmethod
    def truncate(filename: str) -> str:
        idx = filename.index("telepy")
        return filename[idx:]

    def setUp(self):
        clazz = type(self)
        print()
        logging.info(
            f"setUp: {self.truncate(inspect.getfile(clazz))}.{clazz.__qualname__}.{self._testMethodName}"  # noqa: E501
        )

    def tearDown(self):
        clazz = type(self)
        logging.info(
            f"tearDown: {self.truncate(inspect.getfile(clazz))}.{clazz.__qualname__}.{self._testMethodName}"  # noqa: E501
        )
