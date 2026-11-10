from pathlib import Path
import math
import time

class Predictor:
    def __init__(self, model = None):
        import torch

        torch.set_num_threads(1)
        # A second predictor in the same process must not set the interop threads again.
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        model = model or Path(__file__).parent / 'models/torok.ts'
        # A model path named "sine" selects the non-learned SInE control instead of a network.
        self.sine = Path(model).name == 'sine'
        self.model = None if self.sine else torch.jit.load(str(model), map_location = 'cpu').eval()
        self.torch = torch

    def predict(self, matrix):
        from connections_vendor.axiom_prediction.graph import build_axiom_graph
        from connections_vendor.axiom_prediction.representation.schema import node_types, relations

        started = time.monotonic()
        conjectures = list(matrix.conjecture_clauses)
        axioms = [i for i in range(len(matrix.clauses)) if i not in set(conjectures)]
        example = build_axiom_graph(matrix, axiom_clause_ids = axioms, conjecture_clause_ids = conjectures)
        graph = example.graph
        torch = self.torch

        widths = [2, 4, 1, 1, 1]
        nodes = [torch.tensor(graph.nodes[name], dtype = torch.long).reshape(-1, width) for name, width in zip(node_types[:5], widths)]
        edges = [torch.tensor(graph.edges[name], dtype = torch.long).reshape(-1, 3 if positioned else 2) for name, _, _, positioned in relations[:7]]
        graph_s = time.monotonic() - started
        weights = [1.0] * len(matrix.clauses)

        if self.sine:
            from connections_vendor.axiom_prediction.sine import clause_scores
            probabilities = clause_scores(graph, axioms, conjectures)
        else:
            with torch.inference_mode():
                logits = self.model(nodes, edges, torch.tensor(axioms, dtype = torch.long), torch.tensor(conjectures, dtype = torch.long))
                probabilities = logits.sigmoid().tolist()

        for index, value in zip(axioms, probabilities, strict = True):
            if not math.isfinite(value):
                raise ValueError('Model produced a non-finite probability')

            weights[index] = max(1e-6, value)

        return weights, {'graph_s': graph_s, 'inference_s': time.monotonic() - started - graph_s, 'axioms': len(axioms), 'clauses': len(weights)}

def save_weights(path, weights):
    Path(path).write_text(str(len(weights)) + '\n' + '\n'.join(map(str, weights)) + '\n')
