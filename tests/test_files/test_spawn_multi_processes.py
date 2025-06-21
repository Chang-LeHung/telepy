from multiprocessing import Process, set_start_method


def bar():
    print("bar")


def foo():
    print("foo")


def test():
    p1 = Process(target=bar)
    p1.start()
    p2 = Process(target=foo)
    p2.start()

    p1.join()
    p2.join()


if __name__ == "__main__":
    set_start_method("spawn")
    p1 = Process(target=bar)
    p1.start()
    p2 = Process(target=foo)
    p2.start()

    p1.join()
    p2.join()

    p3 = Process(target=test)

    p3.start()
    p3.join()
