
#include "tree.h"
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <queue>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>


std::mutex queue_mtx;
std::condition_variable queue_cv;
std::queue<StackTree*> delete_queue;
std::atomic<bool> thread_initialized{false};
std::thread* delete_thread = nullptr;


struct Node {
    std::string name;
    unsigned long cnt;      // called count
    unsigned long acc_cnt;  // accumulated count
    Node* child;
    Node* sibling;

    // no virtual destructor to save memory
    ~Node() {
        delete child;
        delete sibling;
    }
};


void
split(const char* s, char delim, std::vector<std::string>& elems) {
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, delim)) {
        elems.push_back(item);
    }
}


struct StackTree {
    Node* root;
#define NAME "root"
#define DLIM ';'

    StackTree() {
        root = new Node();
        root->child = nullptr;
        root->sibling = nullptr;
        root->name = NAME;
    }

    // callstack exmplae: main.py:hello:world
    void AddCallStack(const char* callstack) {
        std::vector<std::string> names;
        split(callstack, DLIM, names);
        auto node = root;
        for (const auto& s : names) {
            assert(node != nullptr);
            node->acc_cnt++;
            if (node->child != nullptr) {
                Node* next = node->child;
                Node* prev = nullptr;
                while (next != nullptr && next->name != s) {
                    // optimize for most common case
                    if (prev != nullptr && prev->acc_cnt < next->acc_cnt) {
                        std::swap(prev->name, next->name);
                        std::swap(prev->cnt, next->cnt);
                        std::swap(prev->acc_cnt, next->acc_cnt);
                        std::swap(prev->child, next->child);
                    }
                    prev = next;
                    next = next->sibling;
                }
                if (next != nullptr) {
                    node = next;
                } else {
                    assert(prev != nullptr);
                    Node* new_node = new Node();
                    prev->sibling = new_node;
                    node = new_node;
                    node->name = s;
                }
            } else {
                Node* new_node = new Node();
                node->child = new_node;
                node = new_node;
                node->name = s;
            }
        }
        node->cnt++;  // only leaf node can increment count
        node->acc_cnt++;
    }

    void Save(std::ostream& out) {
        std::vector<std::string> res;
        std::function<void(Node*)> f = [&](Node* node) {
            if (node == nullptr) {
                return;
            }

            // ignore root
            if (node->name != NAME) {
                res.emplace_back(node->name);
            }

            f(node->child);

            if (node->cnt > 0) {
                for (size_t i = 0; i < res.size(); ++i) {
                    out << res[i];
                    if (i + 1 < res.size()) {
                        out << DLIM;
                    }
                }
                out << ' ' << node->cnt << '\n';
            }

            if (node->name != NAME) {
                res.pop_back();
            }

            f(node->sibling);
        };
        f(root);
    }

    virtual ~StackTree() { delete root; }
};

StackTree*
NewTree() {
    return new StackTree();
}


void
DeleteWorker() {
    while (true) {
        std::unique_lock<std::mutex> lock(queue_mtx);
        queue_cv.wait(lock, [] { return !delete_queue.empty(); });

        StackTree* tree = delete_queue.front();
        delete_queue.pop();
        lock.unlock();

        delete tree;
    }
}


void
FreeTree(StackTree* tree) {
    if (!thread_initialized.exchange(true)) {
        // Initialize the background thread only once
        delete_thread = new std::thread(DeleteWorker);
        delete_thread->detach();  // Run in background
    }

    // Add the tree to the deletion queue
    {
        std::lock_guard<std::mutex> lock(queue_mtx);
        delete_queue.push(tree);
    }
    queue_cv.notify_one();  // Notify the worker thread
}

void
Dump(StackTree* tree, const char* filename) {
    std::ofstream out(filename);
    tree->Save(out);
    out.close();
}

char*
Dumps(StackTree* tree) {
    std::ostringstream s;
    tree->Save(s);
    char* res = (char*)malloc(s.str().size() + 1);
    // use memcpy
    memcpy(res, s.str().c_str(), s.str().size() + 1);
    return res;  // move res to caller
}

void
AddCallStack(StackTree* tree, const char* callstack) {
    tree->AddCallStack(callstack);
}


#ifdef TELEPY_TEST


#define Green "\033[32m"
#define Reset "\033[0m"
#define SuccessMessage(msg) Green msg Reset


void
TestCaseSingle() {
    auto tree = new StackTree();
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    std::ostringstream s;
    tree->Save(s);
    assert(s.str() == "main.py;hello;world 4\n");
    std::cout << SuccessMessage("Test case single stack trace passed")
              << std::endl;
    delete tree;
}


void
TestCaseMultiply() {
    auto tree = new StackTree();
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;world");
    std::ostringstream s;
    tree->Save(s);
    assert(s.str() == "main.py;hello;world 3\nmain.py;hello;x 1\n");
    std::cout << SuccessMessage("Test case multiply stack traces passed")
              << std::endl;
    delete tree;
}


void
TestCaseOrderExchange() {
    auto tree = new StackTree();
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("main.py;hello;c");
    std::ostringstream s;
    tree->Save(s);
    std::string res = "main.py;hello;x 8\n";
    res += "main.py;hello;b 6\n";
    res += "main.py;hello;world 3\n";
    res += "main.py;hello;c 1\n";
    assert(s.str() == res);
    std::cout << SuccessMessage("Test case order exchange passed")
              << std::endl;
    delete tree;
}


void
TestCaseComplicated() {
    auto tree = new StackTree();
    tree->AddCallStack("MainThread;main.py;hello;world");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;x");
    tree->AddCallStack("main.py;hello;world");
    tree->AddCallStack("main.py;hello;b");
    tree->AddCallStack("MainThread;main.py;hello;world");

    std::ostringstream s;
    tree->Save(s);
    std::string res = "MainThread;main.py;hello;world 2\n";
    res += "main.py;hello;world 2\n";
    res += "main.py;hello;x 1\n";
    res += "main.py;hello;b 1\n";
    assert(s.str() == res);
    std::cout << SuccessMessage("Test case complicated passed") << std::endl;
    delete tree;
}


int
main() {
    TestCaseSingle();
    TestCaseMultiply();
    TestCaseOrderExchange();
    TestCaseComplicated();
}
#endif