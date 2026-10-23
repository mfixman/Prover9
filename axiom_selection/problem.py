import re
from pathlib import Path
from environment import connections_root

connections_root()
from connections.parsing.tptp.parser import parse_tptp_file
from connections.parsing.tptp.transformer import StmtCNF
from connections.clausification import make_matrix_from_cnf_statements
from connections.syntax.formula import Variable

def load_problem(path, tptp):
    document = parse_tptp_file(path, source_roots = (Path(tptp).resolve(),))
    if any(not isinstance(statement, StmtCNF) for statement in document.statements):
        raise ValueError('This adapter requires shared CNF inputs; clausify FOF explicitly first.')

    return make_matrix_from_cnf_statements(document.statements)

def symbol_text(symbol):
    if symbol in ('=', 'equal___', '$true', '$false'):
        return {'=': '=', 'equal___': '=', '$true': '$T', '$false': '$F'}[symbol]

    if re.fullmatch('[a-z][A-Za-z0-9_]*', symbol):
        return symbol

    raise ValueError(f'Unsupported symbol {symbol!r}; numeric and distinct objects need explicit encoding.')

def term_text(term, variables):
    if isinstance(term, Variable):
        if term not in variables:
            variables[term] = f'V{len(variables)}'

        return variables[term]

    name = symbol_text(term.symbol)
    args = [term_text(arg, variables) for arg in term.args]
    if name == '=':
        return f'({args[0]} = {args[1]})'

    return f'{name}({",".join(args)})' if args else name

def clause_text(clause):
    variables = {}
    literals = [
        ('' if literal.polarity else '-') + term_text(literal.atom, variables)
        for literal in clause.literals
    ]
    return ' | '.join(literals) or '$F'

def prover_input(matrix, seconds = 20, memory = 512):
    options = [
        'set(prolog_style_variables).', f'assign(max_seconds,{max(1, int(seconds))}).',
        f'assign(max_megs,{memory}).', 'clear(print_given).',
        'clear(print_initial_clauses).', 'clear(print_kept).', 'formulas(assumptions).',
    ]
    clauses = [
        f'{clause_text(clause)} # label(torok_input_{i}).'
        for i, clause in enumerate(matrix.clauses)
    ]
    return '\n'.join(options + clauses + ['end_of_list.', ''])
