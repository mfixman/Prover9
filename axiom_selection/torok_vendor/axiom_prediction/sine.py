# Clause-level basic SInE on the axiom graph (vendored from Connections; scores are 1 for selected axioms).

from collections import Counter, defaultdict

def select(axioms, conjecture_symbols):
    frequencies = Counter(symbol for symbols in axioms for symbol in symbols)
    triggers = defaultdict(list)
    for index, symbols in enumerate(axioms):
        if symbols:
            least = min(map(frequencies.__getitem__, symbols))
            for symbol in symbols:
                if frequencies[symbol] == least:
                    triggers[symbol].append(index)

    active = set(conjecture_symbols)
    pending = list(active)
    scores = [0.0] * len(axioms)
    while pending:
        for index in triggers.get(pending.pop(), ()):
            if scores[index]:
                continue

            scores[index] = 1.0
            new = axioms[index] - active
            active.update(new)
            pending.extend(new)

    return scores

def graph_symbols(graph):
    symbols = dict(graph.edges["sym"])
    children = defaultdict(list)
    for parent, child, *_ in graph.edges["arg_term"]:
        children[parent].append(child)

    atoms = dict(graph.edges["atom"])
    clauses = [set() for _ in graph.nodes["clause"]]
    visited = [set() for _ in clauses]
    for clause, literal in graph.edges["contains"]:
        pending = [atoms[literal]]
        while pending:
            term = pending.pop()
            if term in visited[clause]:
                continue

            visited[clause].add(term)
            clauses[clause].add(symbols[term])
            pending.extend(children[term])

    return clauses

def clause_scores(graph, axiom_clause_ids, conjecture_clause_ids):
    symbols = graph_symbols(graph)
    conjecture = set()
    for index in conjecture_clause_ids:
        conjecture.update(symbols[index])

    return select([symbols[index] for index in axiom_clause_ids], conjecture)
