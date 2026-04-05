traditionally, we have three

if

for

while


these 3 above all direct program flow

however, I think that it makes sense to
consider functions a form of control flow
too, as whenever one executes a function,
there is a "diversion" into the code
written in the function definition,
and then possibly a diversion back
with the return value(s) (or error(s)?)
looping back to where the function
was called from (if the function
returns successfully and doesn't
throw an error!) -- and errors,
both simple and "properly handled"
are another way control flow gets
diverted, with one possible
outcome being (premature?)
halting of the program

likewise, object oriented
structures like classes
similarly are in some sense
control structures, because
upon instantiation of an object
and then potentially with executing
methods on that object, control
flow is also "diverted" in an
adjacent way to what happens with
more "simple" structures like
ordinary (non-class) functions

what we will explore next however
is iterators, which also i think
qualify as control structures,
though they're integrated tightly
with the certain iterable data
types and/or structures in python,
namely:

lists

tuples

dictionaries

