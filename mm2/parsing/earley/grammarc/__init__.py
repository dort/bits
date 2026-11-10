"""Grammar specification compiler for the MM2 Earley engines.

`spec` validates and compiles the versioned grammar JSON; `serialize` turns a
compiled grammar into the `grm-*` facts the engines consume, plus the demand
and round-table facts of the engine input contract.
"""

from .spec import CompiledGrammar, Production, compile_grammar, load_grammar
from .serialize import (MAX_ROUNDS, demand_fact, grammar_facts,
                        round_table_facts)

__all__ = ["CompiledGrammar", "Production", "compile_grammar", "load_grammar",
           "MAX_ROUNDS", "demand_fact", "grammar_facts", "round_table_facts"]
