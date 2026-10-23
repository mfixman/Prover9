#include "selection.h"
#include "../ladr/clauseid.h"
#include "../ladr/just.h"
#include <stdint.h>
#include <math.h>

static double *input_weights, *weights, *tree;
static Topform *active;
static int capacity, input_count, enabled = -1;
static uint64_t random_state = 1;
static double strength = 1.0;
static int soft_enabled = -1;
static int tie_only = 0;

static void reserve(int id) {
  if (id < capacity) return;
  int old = capacity;
  capacity = capacity ? capacity : 1024;
  while (capacity <= id) capacity *= 2;

  weights = realloc(weights, capacity * sizeof(double));
  active = realloc(active, capacity * sizeof(Topform));
  free(tree);
  tree = calloc(capacity, sizeof(double));
  if (!weights || !active || !tree) fatal_error("Torok allocation failed");

  memset(weights + old, 0, (capacity - old) * sizeof(double));
  memset(active + old, 0, (capacity - old) * sizeof(Topform));
  for (int i = 1; i < capacity; i++) {
    tree[i] += active[i] ? weights[i] : 0;
    int next = i + (i & -i);
    if (next < capacity) tree[next] += tree[i];
  }
}

BOOL torok_enabled(void) {
  if (enabled >= 0) return enabled;
  const char *path = getenv("PROVER9_TOROK_WEIGHTS");
  enabled = path && *path;
  if (!enabled) return FALSE;

  FILE *file = fopen(path, "r");
  if (!file || fscanf(file, "%d", &input_count) != 1 || input_count < 0)
    fatal_error("Torok cannot read weight file");
  input_weights = malloc((input_count + 1) * sizeof(double));
  if (!input_weights) fatal_error("Torok allocation failed");

  for (int i = 0; i < input_count; i++) {
    if (fscanf(file, "%lf", input_weights + i) != 1 ||
        !isfinite(input_weights[i]) || input_weights[i] <= 0 || input_weights[i] > 1)
      fatal_error("Torok invalid probability");
  }

  fclose(file);
  const char *setting = getenv("PROVER9_TOROK_STRENGTH");
  if (setting) strength = strtod(setting, NULL);
  if (!isfinite(strength) || strength < 0) fatal_error("Torok invalid strength");
  const char *seed = getenv("PROVER9_TOROK_SEED");
  if (seed) random_state = strtoull(seed, NULL, 10);
  printf("\n%% Torok: %d input scores; mode %s.\n", input_count, torok_soft() ? "Soft" : "Sample");
  return TRUE;
}

static double probability(Topform clause) {
  if (!clause || clause->id <= 0) return 1.0;
  int id = clause->id;
  reserve(id);
  if (weights[id] > 0) return weights[id];

  char *label;
  for (int i = 1; (label = get_string_attribute(clause->attributes, label_att(), i)); i++) {
    int index;
    if (sscanf(label, "torok_input_%d", &index) == 1) {
      if (index < 0 || index >= input_count) fatal_error("Torok input label mismatch");
      return weights[id] = input_weights[index];
    }
  }

  double sum = 0;
  int count = 0;
  Ilist parents = get_parents(clause->justification, TRUE);
  for (Ilist p = parents; p; p = p->next) {
    if (p->i > 0 && p->i < id) {
      sum += log(probability(find_clause_by_id(p->i)));
      count++;
    }
  }

  zap_ilist(parents);
  return weights[id] = count ? exp(sum / count) : 1.0;
}

BOOL torok_soft(void) {
  if (soft_enabled >= 0) return soft_enabled;
  const char *mode = getenv("PROVER9_TOROK_MODE");
  tie_only = mode && strcmp(mode, "Tie") == 0;
  soft_enabled = tie_only || (mode && strcmp(mode, "Soft") == 0);
  return soft_enabled;
}

Ordertype torok_compare(Topform a, Topform b) {
  if (tie_only) {
    if (a->weight < b->weight) return LESS_THAN;
    if (a->weight > b->weight) return GREATER_THAN;
    double pa = probability(a), pb = probability(b);
    if (pa > pb) return LESS_THAN;
    if (pa < pb) return GREATER_THAN;
    return cl_id_compare(a, b);
  }
  double x = a->weight / (1.0 + strength * probability(a));
  double y = b->weight / (1.0 + strength * probability(b));
  if (x < y) return LESS_THAN;
  if (x > y) return GREATER_THAN;
  if (a->id < b->id) return LESS_THAN;
  if (a->id > b->id) return GREATER_THAN;
  return SAME_AS;
}

void torok_update(Topform clause, BOOL insert) {
  if (!torok_enabled()) return;
  int id = clause->id;
  if (id <= 0) fatal_error("Torok requires assigned clause IDs");
  double weight = probability(clause);
  if (torok_soft()) return;
  double delta = insert ? weight : -weight;
  if (!!active[id] == !!insert) fatal_error("Torok queue membership mismatch");

  active[id] = insert ? clause : NULL;
  for (int i = id; i < capacity; i += i & -i) tree[i] += delta;
}

static double uniform(void) {
  uint64_t value = (random_state += UINT64_C(0x9e3779b97f4a7c15));
  value = (value ^ (value >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
  value = (value ^ (value >> 27)) * UINT64_C(0x94d049bb133111eb);
  value ^= value >> 31;
  return ((value >> 11) + 0.5) * (1.0 / 9007199254740992.0);
}

Topform torok_pick(void) {
  double total = 0;
  for (int i = capacity - 1; i > 0; i -= i & -i) total += tree[i];
  if (total <= 0) fatal_error("Torok empty weighted queue");
  double target = uniform() * total;
  int index = 0;

  for (int step = capacity / 2; step; step /= 2) {
    int next = index + step;
    if (next < capacity && tree[next] <= target) {
      target -= tree[next];
      index = next;
    }
  }

  if (index + 1 >= capacity || !active[index + 1]) fatal_error("Torok sampling failed");
  return active[index + 1];
}
