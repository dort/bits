#!/usr/bin/env python3
"""A simple family tree program that collects family member information."""


def get_user_info():
    """Get the user's name and their parents' names."""
    print("=== Family Tree Builder ===\n")

    user_name = input("Enter your name: ").strip()

    print("\nNow enter your parents' names:")
    mother_name = input("Enter your mother's name: ").strip()
    father_name = input("Enter your father's name: ").strip()

    couple = {
        "mother": mother_name,
        "father": father_name
    }

    return user_name, couple


def add_family_members(family_tree, couple):
    """Allow user to add additional family members."""
    print("\n--- Add Family Members ---")
    print("You can add siblings, grandparents, or other relatives.")
    print("Enter 'done' when finished.\n")

    while True:
        relation = input("Enter relationship (e.g., sibling, grandparent) or 'done': ").strip().lower()
        if relation == 'done':
            break

        name = input(f"Enter {relation}'s name: ").strip()

        # Special handling for grandparents
        if relation == 'grandparent':
            print(f"\nWhich parent is {name}'s child?")
            print(f"  1. {couple['mother']} (mother)")
            print(f"  2. {couple['father']} (father)")
            choice = input("Enter 1 or 2: ").strip()

            if choice == '1':
                parent_side = 'maternal'
            elif choice == '2':
                parent_side = 'paternal'
            else:
                print("Invalid choice. Defaulting to maternal side.")
                parent_side = 'maternal'

            key = f"{parent_side}_grandparent"
            if key not in family_tree:
                family_tree[key] = []
            family_tree[key].append(name)
            print(f"Added {name} as {parent_side} grandparent.\n")
        else:
            if relation not in family_tree:
                family_tree[relation] = []
            family_tree[relation].append(name)
            print(f"Added {name} as {relation}.\n")


def print_family_tree(user_name, couple, family_tree):
    """Print the family tree in a visual format."""
    print("\n" + "=" * 50)
    print("              FAMILY TREE")
    print("=" * 50)

    # Print grandparents if any
    maternal_gp = family_tree.get('maternal_grandparent', [])
    paternal_gp = family_tree.get('paternal_grandparent', [])

    if maternal_gp or paternal_gp:
        print("\n           Grandparents")
        print("           ------------")

        if paternal_gp:
            paternal_names = ", ".join(paternal_gp)
            print(f"  Paternal: {paternal_names}")
            print(f"       |")

        if maternal_gp:
            maternal_names = ", ".join(maternal_gp)
            print(f"                              Maternal: {maternal_names}")
            print(f"                                   |")

        print()

    # Print parents
    print("              Parents")
    print("              -------")
    print(f"        {couple['father']} + {couple['mother']}")
    print("                |")
    print("                v")

    # Print user
    print(f"           [{user_name}] (You)")

    # Print siblings if any
    if 'sibling' in family_tree:
        siblings = ", ".join(family_tree['sibling'])
        print(f"        Siblings: {siblings}")

    # Print other relatives (excluding grandparents and siblings)
    skip_relations = ['sibling', 'maternal_grandparent', 'paternal_grandparent']
    other_relations = [r for r in family_tree if r not in skip_relations]
    if other_relations:
        print("\n        Other Relatives:")
        for relation in other_relations:
            members = ", ".join(family_tree[relation])
            print(f"          {relation.title()}(s): {members}")

    print("\n" + "=" * 50)

    # Print raw variables
    print("\n--- Raw Variables ---")
    print(f"user_name = {repr(user_name)}")
    print(f"couple = {couple}")
    print(f"family_tree = {family_tree}")


def main():
    """Main function to run the family tree program."""
    # Get user and parents info
    user_name, couple = get_user_info()

    print(f"\nHello {user_name}!")
    print(f"Your parents are {couple['father']} (father) and {couple['mother']} (mother).")

    # Initialize family tree with additional members
    family_tree = {}

    # Ask if user wants to add more family members
    add_more = input("\nWould you like to add more family members? (yes/no): ").strip().lower()
    if add_more in ('yes', 'y'):
        add_family_members(family_tree, couple)

    # Print the family tree
    print_family_tree(user_name, couple, family_tree)


if __name__ == "__main__":
    main()
