#ifndef TOROK_SELECTION_H
#define TOROK_SELECTION_H
#include "../ladr/topform.h"
void torok_update(Topform clause, BOOL insert);
BOOL torok_enabled(void);
BOOL torok_soft(void);
Ordertype torok_compare(Topform a, Topform b);
Topform torok_pick(void);
#endif
