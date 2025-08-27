import threading
import time


def compute_heavy_task():
    """A compute-intensive task"""
    result = 0
    for i in range(100000):
        result += i * i
    return result


def io_task():
    """A task that includes IO operations"""
    # Use standard library functions
    import json

    data = {"test": "data", "numbers": list(range(100))}
    json_str = json.dumps(data)
    parsed = json.loads(json_str)
    return len(parsed)


def threading_task():
    """A multi-threading task"""

    def worker():
        time.sleep(0.01)
        return compute_heavy_task()

    threads = []
    for i in range(3):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()


def main():
    """Main function"""
    print("Starting focus and regex test...")

    # Execute compute task
    result1 = compute_heavy_task()
    print(f"Heavy task result: {result1}")

    # Execute IO task
    result2 = io_task()
    print(f"IO task result: {result2}")

    # Execute multi-threading task
    threading_task()
    print("Threading task completed")

    print("All tasks completed!")


if __name__ == "__main__":
    main()
