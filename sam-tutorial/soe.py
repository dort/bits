#! /usr/bin/python3
# Sieve of Eratoshtenes

import math
from pprint import pprint as pp

# prime finder
def pf(upper_bound=1000):
    primes = []
    
    for i in range(2, upper_bound + 1):
        is_prime = True
        for j in primes:
            if j * j > i:
                break
            if i % j == 0:
                is_prime = False
                break

            
        if is_prime:
            primes.append(i)
            

            
    return primes




if __name__ == "__main__":
    res=pf(10000)
    print(res, len(res))

