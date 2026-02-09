import random

def random_tuple(length=3000):
    result = tuple(random.randint(0, 1) for _ in range(length))
    return result


def multiple_RTs(num=10):
    result = [random_tuple(10) for _ in range(num)]
    return result


def main():
    a = multiple_RTs(20)
    for i in range(len(a)):
        print(a[i])


if __name__ == "__main__":
    main()


                           
