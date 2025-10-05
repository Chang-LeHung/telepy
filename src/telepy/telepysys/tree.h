
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
AddCallStackWithCount(struct StackTree* tree,
                      const char* callstack,
                      unsigned long cnt);


void
Dump(struct StackTree* tree, const char* filename);

// returns a string that should be freed by caller (ownership returned )
char*
Dumps(struct StackTree* tree);

#ifdef __cplusplus
}
#endif

#endif