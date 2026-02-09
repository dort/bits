# Sieve of Eratoshtenes

import math
from pprint import pprint as pp

# prime finder


def pf(upper_bound=1000) :
    primes = []
    for (i := 1 to upper_bound):
        i++
        for (j in primes):
            if i/j != float(i)/float(j) for all j:
                primes.append(j)

        if i = 1000:
            break

    return primes
        
