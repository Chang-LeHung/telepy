from multiprocessing import Process, set_start_method


def test_forkserver(name):
    print("hello", name)
    a = 0
    while a < 1000000:
        a += 1


if __name__ == "__main__":
    set_start_method("forkserver")
    p = Process(target=test_forkserver, args=("bob",))
    p.start()
    p.join()
