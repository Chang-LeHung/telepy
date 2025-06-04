
#ifndef TELE_TREE_H
#define TELE_TREE_H

#ifdef __cplusplus
extern "C" {
#endif

struct StackTree;

struct StackTree*
NewTree();

void
FreeTree(struct StackTree* tree);

void
AddCallStack(struct StackTree* tree, const char* callstack);

void
Dump(struct StackTree* tree, const char* filename);

#ifdef __cplusplus
}
#endif

#endif