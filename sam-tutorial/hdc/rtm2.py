import random
import math


'''sparsity converter
metric input must be 1 or greater
for values of metric between 1 and e, density of 1s will be less than .5
for metric = e, the probability will be equal for 0s and 1s
for metric > e, density of 1s will be greater than .5
'''
def sc(metric = math.e) :
    density = 0.5 * (math.log(metric))
    print(metric, density)
    return density



def random_tuple(length=3000, sparsity=0.5):

    result = tuple(random.choices([0, 1], weights=[1.0-sparsity, sparsity], k=length))
    
    return result


def multiple_RTs(num=10):
    result = [random_tuple(length=10, sparsity=sc(math.e)) for _ in range(num)]
    return result


def main():
    a = multiple_RTs()
    for  b in a :
        print(b)


if __name__ == "__main__":
    main()


                           
