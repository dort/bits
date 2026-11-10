"""Grammar compiler and MORK runner for the MM2 Earley engines.

`spec` validates and compiles the versioned grammar JSON; `serialize` turns a
compiled grammar into the `grm-*` facts the engines consume, plus the demand
and round-table facts of the engine input contract; `facts` parses engine
dumps and computes the canonical semantic projection; `runner` orchestrates
per-unit recognition over version-2 token bundles with doubling sweep budgets
and the accepted/rejected/incomplete contract.
"""

from .spec import CompiledGrammar, Production, compile_grammar, load_grammar
from .serialize import (MAX_ROUNDS, demand_fact, grammar_facts,
                        round_table_facts)
from .facts import (FOREST_HEADS, RECOGNITION_HEADS, parse_facts, projection,
                    render, select)
from .forest import Forest
from .runner import Runner, UnitResult

__all__ = ["CompiledGrammar", "Production", "compile_grammar", "load_grammar",
           "MAX_ROUNDS", "demand_fact", "grammar_facts", "round_table_facts",
           "FOREST_HEADS", "RECOGNITION_HEADS", "parse_facts", "projection",
           "render", "select", "Forest", "Runner", "UnitResult"]
