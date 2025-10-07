
#pragma once

#include <stddef.h>  // for NULL and offsetof

struct list_head {
    struct list_head *next, *prev;
};

#define INIT_LIST_HEAD(ptr)                                                   \
    do {                                                                      \
        (ptr)->next = (ptr);                                                  \
        (ptr)->prev = (ptr);                                                  \
    } while (0)


// offsetof is already defined in <stddef.h>, no need to redefine
#define container_of(ptr, type, member)                                       \
    ((type*)((char*)(ptr) - offsetof(type, member)))

#define list_entry(ptr, type, member) container_of(ptr, type, member)

#define list_for_each(pos, head)                                              \
    for (pos = (head)->next; pos != (head); pos = pos->next)

#define list_for_each_entry(pos, head, member)                                \
    for (pos = list_entry((head)->next, typeof(*pos), member);                \
         &pos->member != (head);                                              \
         pos = list_entry(pos->member.next, typeof(*pos), member))

#define list_for_each_entry_safe(pos, n, head, member)                        \
    for (pos = list_entry((head)->next, typeof(*pos), member),                \
        n = list_entry(pos->member.next, typeof(*pos), member);               \
         &pos->member != (head);                                              \
         pos = n, n = list_entry(n->member.next, typeof(*n), member))


static inline void
list_add(struct list_head* new, struct list_head* head) {
    new->next = head->next;
    new->prev = head;
    head->next->prev = new;
    head->next = new;
}

static inline void
list_add_tail(struct list_head* new, struct list_head* head) {
    new->next = head;
    new->prev = head->prev;
    head->prev->next = new;
    head->prev = new;
}

static inline void
list_del(struct list_head* entry) {
    entry->next->prev = entry->prev;
    entry->prev->next = entry->next;
    entry->next = entry->prev = NULL;  // avoid dangling pointers
}

static inline int
list_empty(const struct list_head* head) {
    return head->next == head;
}
