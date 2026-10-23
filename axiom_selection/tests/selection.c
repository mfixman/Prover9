#include "../selection.c"
#include "../../ladr/top_input.h"
#include <assert.h>

int main(void) {
  init_standard_ladr();
  register_attribute("label", STRING_ATTRIBUTE);
  enabled = 1;
  input_count = 2;
  double values[] = {0.1, 0.9};
  input_weights = values;

  Topform first = get_topform(), second = get_topform();
  assign_clause_id(first);
  assign_clause_id(second);
  first->attributes = set_string_attribute(NULL, label_att(), "torok_input_0");
  second->attributes = set_string_attribute(NULL, label_att(), "torok_input_1");
  torok_update(first, TRUE);
  torok_update(second, TRUE);

  int count = 0;
  for (int i = 0; i < 100000; i++) count += torok_pick() == first;
  assert(count > 9700 && count < 10300);
  torok_update(first, FALSE);
  for (int i = 0; i < 100; i++) assert(torok_pick() == second);

  Topform child = get_topform();
  assign_clause_id(child);
  child->justification = binary_res_just(first, 1, second, 1);
  assert(fabs(probability(child) - 0.3) < 1e-12);
  torok_update(child, TRUE);
  reserve(100000);
  torok_update(second, FALSE);
  for (int i = 0; i < 100; i++) assert(torok_pick() == child);

  torok_update(child, FALSE);
  torok_update(first, TRUE);
  assert(torok_pick() == first);
  first->weight = 10;
  second->weight = 12;
  assert(torok_compare(first, second) == GREATER_THAN);
  second->weight = 30;
  assert(torok_compare(first, second) == LESS_THAN);
  assert(torok_compare(first, first) == SAME_AS);

  printf("Weighted frequencies, deletion, growth, and parent inheritance passed.\n");
  return 0;
}
