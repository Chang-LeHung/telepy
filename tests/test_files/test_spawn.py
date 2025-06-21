from multiprocessing import Process, set_start_method


def f(name):
    print("hello", name)


if __name__ == "__main__":
    set_start_method("spawn")
    p = Process(target=f, args=("bob",))
    p.start()
    p.join()
