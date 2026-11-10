#ifndef WEIGHTED_SELECTION_H
#define WEIGHTED_SELECTION_H
#include "../ladr/topform.h"
void weighted_update(Topform clause, BOOL insert);
BOOL weighted_enabled(void);
BOOL weighted_soft(void);
Ordertype weighted_compare(Topform a, Topform b);
Topform weighted_pick(void);
#endif
