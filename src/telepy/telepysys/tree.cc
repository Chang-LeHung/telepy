
#include "tree.h"
#include <unordered_map>
#include <string>
#include <vector>
#include <sstream>
#include <cassert>
#include <utility>
#include <cstdio>
#include <iostream>

struct Node {
    int idx;   // name idx in symbol table
    long cnt;  // called count
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
    std::unordered_map<std::string, int> symbols;
    Node* root;

#define ContainSymbol(s) (symbols.find(s) != symbols.end())

    StackTree() {
        root = new Node();
        root->child = nullptr;
        root->sibling = nullptr;
        AddNode(root, "root");
    }

    void AddNode(Node* node, const std::string& name) {
        auto it = symbols.find(name);
        if (it == symbols.end()) {
            symbols[name] = symbols.size();
        }
        node->idx = symbols[name];
    }

    // callstack exmplae: main.py:hello:world
    void AddCallStack(const char* callstack) {
        std::vector<std::string> names;
        split(callstack, ':', names);
        auto& node = root;
        for (const auto& s : names) {
            assert(node != nullptr);
            if (__builtin_expect(!ContainSymbol(s), false)) {
                // fast path
                // insert new node instead of searching
                Node* new_node = new Node();
                if (node->child == nullptr) {
                    node->child = new_node;
                } else {
                    new_node->sibling = node->child->sibling;
                    node->child->sibling = new_node;
                }
                AddNode(new_node, s);
                node = new_node;
            } else {
                // slow path
                if (node->child != nullptr) {
                    Node* next = node->child;
                    Node* prev = nullptr;
                    while (next != nullptr && next->idx != symbols[s]) {
                        // optimize for most common case
                        if (prev != nullptr && prev->cnt < next->cnt) {
                            std::swap(node->idx, next->idx);
                            std::swap(node->cnt, next->cnt);
                            std::swap(node->child, next->child);
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
                        AddNode(new_node, s);
                        node = new_node;
                    }
                } else {
                    Node* new_node = new Node();
                    node->child = new_node;
                    AddNode(new_node, s);
                    node = new_node;
                }
            }
        }
        node->cnt++;  // only leaf node can increment count
    }

    void traverse(Node* node, std::function<void(Node*)> func) {
        func(node);
        if (node->child != nullptr) {
            traverse(node->child, func);
        }
        if (node->sibling != nullptr) {
            traverse(node->sibling, func);
        }
    }

    virtual ~StackTree() { delete root; }
};

StackTree*
NewTree() {
    return new StackTree();
}

void
FreeTree(StackTree* tree) {
    delete tree;
}

void
Dump(StackTree* tree, const char* filename) {
    // TODO
}

void
AddCallStack(StackTree* tree, const char* callstack) {
    tree->AddCallStack(callstack);
}


#ifdef TELEPY_TEST
void
TestCase1() {}


void
TestCase2() {}


void
TestCase3() {}


int
main() {
    TestCase1();
    TestCase2();
    TestCase3();
}
#endif