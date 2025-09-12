#!/usr/bin/env python3

import threading
import time


def fib(n):
    """Fibonacci function that should be captured by regex pattern 'fib'"""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def calculate_sum(n):
    """Sum function that should NOT be captured by regex pattern 'fib'"""
    total = 0
    for i in range(n):
        total += i
        time.sleep(0.001)  # Small delay to ensure sampling
    return total


def process_data(data):
    """Data processing function that should NOT be captured by regex pattern 'fib'"""
    result = []
    for item in data:
        result.append(item * 2)
        time.sleep(0.001)  # Small delay to ensure sampling
    return result


def fib_worker():
    """Thread worker that calls fib function"""
    for i in range(5, 8):  # Calculate smaller fib numbers
        fib(i)
        time.sleep(0.005)  # Shorter sleep


def sum_worker():
    """Thread worker that calls calculate_sum function"""
    for i in range(50, 100, 25):  # Smaller ranges
        calculate_sum(i)
        time.sleep(0.005)  # Shorter sleep


def data_worker():
    """Thread worker that calls process_data function"""
    test_data = [1, 2, 3, 4, 5] * 5  # Smaller data
    for _ in range(3):  # Fewer iterations
        process_data(test_data)
        time.sleep(0.005)  # Shorter sleep


def main():
    # Create multiple threads executing different functions
    threads = []

    # Thread 1: fib functions (should be captured)
    t1 = threading.Thread(target=fib_worker, name="FibThread")
    threads.append(t1)

    # Thread 2: sum functions (should NOT be captured)
    t2 = threading.Thread(target=sum_worker, name="SumThread")
    threads.append(t2)

    # Thread 3: data processing functions (should NOT be captured)
    t3 = threading.Thread(target=data_worker, name="DataThread")
    threads.append(t3)

    # Start all threads
    for thread in threads:
        thread.start()

    # Also run some fib in main thread (should be captured)
    main_fib_result = fib(30)  # Smaller number

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print(f"Main thread fib(30) = {main_fib_result}")
    print("All threads completed")


if __name__ == "__main__":
    main()
