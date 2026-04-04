#!/usr/bin/env python3
"""A family tree program that supports unlimited family relationships."""


class FamilyTree:
    """Manages all family members and their relationships."""

    def __init__(self):
        self.members = {}  # name -> person dict
        self.user_name = None
        self.couple = None  # Original couple dict for compatibility

    def add_person(self, name):
        """Add a person to the family tree if not already present."""
        if name not in self.members:
            self.members[name] = {
                'name': name,
                'spouse': None,
                'children': [],
                'parents': []
            }
        return self.members[name]

    def set_spouse(self, person1_name, person2_name):
        """Set two people as spouses."""
        p1 = self.add_person(person1_name)
        p2 = self.add_person(person2_name)
        p1['spouse'] = person2_name
        p2['spouse'] = person1_name

    def add_child(self, parent_name, child_name):
        """Add a child to a parent."""
        parent = self.add_person(parent_name)
        child = self.add_person(child_name)
        if child_name not in parent['children']:
            parent['children'].append(child_name)
        if parent_name not in child['parents']:
            child['parents'].append(parent_name)
        # If parent has spouse, also add as parent of child
        if parent['spouse'] and parent['spouse'] not in child['parents']:
            spouse = self.members[parent['spouse']]
            if child_name not in spouse['children']:
                spouse['children'].append(child_name)
            child['parents'].append(parent['spouse'])

    def add_parent(self, child_name, parent_name):
        """Add a parent to a child."""
        self.add_child(parent_name, child_name)

    def get_siblings(self, person_name):
        """Get siblings of a person (people who share parents)."""
        person = self.members.get(person_name)
        if not person or not person['parents']:
            return []
        siblings = set()
        for parent_name in person['parents']:
            parent = self.members[parent_name]
            for child in parent['children']:
                if child != person_name:
                    siblings.add(child)
        return list(siblings)

    def get_grandparents(self, person_name):
        """Get grandparents of a person."""
        person = self.members.get(person_name)
        if not person:
            return []
        grandparents = []
        for parent_name in person['parents']:
            parent = self.members[parent_name]
            grandparents.extend(parent['parents'])
        return grandparents

    def get_aunts_uncles(self, person_name):
        """Get aunts and uncles (siblings of parents)."""
        person = self.members.get(person_name)
        if not person:
            return []
        aunts_uncles = []
        for parent_name in person['parents']:
            aunts_uncles.extend(self.get_siblings(parent_name))
        return aunts_uncles

    def get_cousins(self, person_name):
        """Get cousins (children of aunts/uncles)."""
        aunts_uncles = self.get_aunts_uncles(person_name)
        cousins = []
        for au in aunts_uncles:
            au_person = self.members[au]
            cousins.extend(au_person['children'])
        return cousins

    def get_all_members_list(self):
        """Get a numbered list of all family members."""
        return list(self.members.keys())

    def display_members_menu(self):
        """Display all members with numbers for selection."""
        members = self.get_all_members_list()
        print("\nFamily members:")
        for i, name in enumerate(members, 1):
            print(f"  {i}. {name}")
        return members

    def select_member(self, prompt="Select a family member"):
        """Let user select a family member by number."""
        members = self.display_members_menu()
        while True:
            choice = input(f"\n{prompt} (enter number): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(members):
                    return members[idx]
                else:
                    print("Invalid number. Try again.")
            except ValueError:
                print("Please enter a number.")


def get_user_info(tree):
    """Get the user's name and their parents' names."""
    print("=== Family Tree Builder ===\n")

    user_name = input("Enter your name: ").strip()
    tree.user_name = user_name
    tree.add_person(user_name)

    print("\nNow enter your parents' names:")
    mother_name = input("Enter your mother's name: ").strip()
    father_name = input("Enter your father's name: ").strip()

    # Store original couple dict for compatibility
    tree.couple = {
        "mother": mother_name,
        "father": father_name
    }

    # Add parents and set them as spouses
    tree.add_person(mother_name)
    tree.add_person(father_name)
    tree.set_spouse(mother_name, father_name)
    tree.add_parent(user_name, mother_name)
    tree.add_parent(user_name, father_name)

    return user_name


def add_family_members(tree):
    """Allow user to add additional family members."""
    print("\n--- Add Family Members ---")
    print("Relationships: sibling, grandparent, great grandparent,")
    print("               aunt, uncle, spouse, child")
    print("Enter 'done' when finished.\n")

    while True:
        relation = input("Enter relationship or 'done': ").strip().lower()
        if relation == 'done':
            break

        if relation == 'sibling':
            name = input("Enter sibling's name: ").strip()
            tree.add_person(name)
            # Siblings share the same parents as user
            user = tree.members[tree.user_name]
            for parent_name in user['parents']:
                tree.add_child(parent_name, name)
            print(f"Added {name} as sibling.\n")

        elif relation == 'grandparent':
            name = input("Enter grandparent's name: ").strip()
            print(f"\nWhich parent is {name}'s child?")
            print(f"  1. {tree.couple['mother']} (mother)")
            print(f"  2. {tree.couple['father']} (father)")
            choice = input("Enter 1 or 2: ").strip()

            if choice == '1':
                parent_name = tree.couple['mother']
            elif choice == '2':
                parent_name = tree.couple['father']
            else:
                print("Invalid choice. Defaulting to mother.")
                parent_name = tree.couple['mother']

            tree.add_parent(parent_name, name)
            print(f"Added {name} as grandparent of {parent_name}.\n")

        elif relation == 'great grandparent':
            name = input("Enter great grandparent's name: ").strip()
            grandparents = tree.get_grandparents(tree.user_name)
            if not grandparents:
                print("No grandparents in tree yet. Add grandparents first.\n")
                continue

            print(f"\nWhich grandparent is {name}'s child?")
            for i, gp in enumerate(grandparents, 1):
                print(f"  {i}. {gp}")
            choice = input("Enter number: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(grandparents):
                    gp_name = grandparents[idx]
                    tree.add_parent(gp_name, name)
                    print(f"Added {name} as great grandparent (parent of {gp_name}).\n")
                else:
                    print("Invalid choice.\n")
            except ValueError:
                print("Invalid input.\n")

        elif relation in ('aunt', 'uncle'):
            name = input(f"Enter {relation}'s name: ").strip()
            print(f"\nWhich parent is {name}'s sibling?")
            print(f"  1. {tree.couple['mother']} (mother)")
            print(f"  2. {tree.couple['father']} (father)")
            choice = input("Enter 1 or 2: ").strip()

            if choice == '1':
                parent_name = tree.couple['mother']
            elif choice == '2':
                parent_name = tree.couple['father']
            else:
                print("Invalid choice. Defaulting to mother.")
                parent_name = tree.couple['mother']

            # Aunt/uncle shares parents with the selected parent
            tree.add_person(name)
            parent = tree.members[parent_name]
            for grandparent_name in parent['parents']:
                tree.add_child(grandparent_name, name)

            if not parent['parents']:
                print(f"Note: {parent_name} has no parents in tree yet.")
                print(f"Adding {name} but relationship incomplete until grandparents added.\n")
            else:
                print(f"Added {name} as {relation} (sibling of {parent_name}).\n")

        elif relation == 'spouse':
            print("\nWho is getting a spouse?")
            person_name = tree.select_member("Select the person")
            spouse_name = input(f"Enter {person_name}'s spouse's name: ").strip()
            tree.set_spouse(person_name, spouse_name)
            print(f"Added {spouse_name} as spouse of {person_name}.\n")

        elif relation == 'child':
            print("\nWho is the parent of this child?")
            parent_name = tree.select_member("Select the parent")
            child_name = input(f"Enter {parent_name}'s child's name: ").strip()
            tree.add_child(parent_name, child_name)
            print(f"Added {child_name} as child of {parent_name}.\n")

        else:
            print(f"Unknown relationship '{relation}'. Try: sibling, grandparent,")
            print("great grandparent, aunt, uncle, spouse, child\n")


def print_family_tree(tree):
    """Print the family tree in a visual format."""
    user_name = tree.user_name
    couple = tree.couple

    print("\n" + "=" * 60)
    print("                    FAMILY TREE")
    print("=" * 60)

    # Print great grandparents if any
    grandparents = tree.get_grandparents(user_name)
    great_grandparents = []
    for gp in grandparents:
        gp_person = tree.members[gp]
        great_grandparents.extend(gp_person['parents'])

    if great_grandparents:
        print("\n  Great Grandparents: " + ", ".join(great_grandparents))
        print("          |")

    # Print grandparents
    maternal_gp = tree.members[couple['mother']]['parents']
    paternal_gp = tree.members[couple['father']]['parents']

    if maternal_gp or paternal_gp:
        print("\n  Grandparents")
        print("  ------------")
        if paternal_gp:
            print(f"    Paternal ({couple['father']}'s parents): {', '.join(paternal_gp)}")
        if maternal_gp:
            print(f"    Maternal ({couple['mother']}'s parents): {', '.join(maternal_gp)}")
        print("          |")

    # Print aunts/uncles
    aunts_uncles = tree.get_aunts_uncles(user_name)
    if aunts_uncles:
        print(f"\n  Aunts/Uncles: {', '.join(aunts_uncles)}")
        # Print cousins (children of aunts/uncles)
        cousins = tree.get_cousins(user_name)
        if cousins:
            print(f"    └─ Cousins: {', '.join(cousins)}")

    # Print parents
    print("\n  Parents")
    print("  -------")
    print(f"    {couple['father']} + {couple['mother']}")
    print("          |")
    print("          v")

    # Print user and siblings
    siblings = tree.get_siblings(user_name)
    print(f"    [{user_name}] (You)", end="")
    if siblings:
        print(f"  &  Siblings: {', '.join(siblings)}")
    else:
        print()

    # Print user's spouse if any
    user_person = tree.members[user_name]
    if user_person['spouse']:
        print(f"      + Spouse: {user_person['spouse']}")

    # Print user's children if any
    if user_person['children']:
        print(f"          |")
        print(f"          └─ Children: {', '.join(user_person['children'])}")
        # Print grandchildren
        for child_name in user_person['children']:
            child = tree.members[child_name]
            if child['spouse']:
                print(f"               {child_name} + {child['spouse']}")
            if child['children']:
                print(f"               └─ {child_name}'s children: {', '.join(child['children'])}")

    # Print extended family (anyone else with children)
    print("\n  Extended Family:")
    printed = {user_name}
    for name, person in tree.members.items():
        if name in printed or name in [couple['mother'], couple['father']]:
            continue
        if person['children'] and name not in user_person['children']:
            children_str = ', '.join(person['children'])
            spouse_str = f" + {person['spouse']}" if person['spouse'] else ""
            print(f"    {name}{spouse_str} -> Children: {children_str}")
            printed.add(name)

    print("\n" + "=" * 60)

    # Print graphical tree
    print_graphical_tree(tree)


def print_graphical_tree(tree):
    """Print a graphical ASCII representation of the family tree."""
    user_name = tree.user_name
    couple = tree.couple

    print("\n" + "=" * 70)
    print("                      GRAPHICAL FAMILY TREE")
    print("=" * 70)

    # Get all generations
    maternal_gp = tree.members[couple['mother']]['parents']
    paternal_gp = tree.members[couple['father']]['parents']

    # Great grandparents level
    great_gp_paternal = []
    great_gp_maternal = []
    for gp in paternal_gp:
        great_gp_paternal.extend(tree.members[gp]['parents'])
    for gp in maternal_gp:
        great_gp_maternal.extend(tree.members[gp]['parents'])

    if great_gp_paternal or great_gp_maternal:
        print("\n  GREAT GRANDPARENTS:")
        line = "  "
        if great_gp_paternal:
            line += "  ".join([f"[{n}]" for n in great_gp_paternal])
        if great_gp_paternal and great_gp_maternal:
            line += "          "
        if great_gp_maternal:
            line += "  ".join([f"[{n}]" for n in great_gp_maternal])
        print(line)
        print("       " + "│" * (len(great_gp_paternal) + len(great_gp_maternal)))

    # Grandparents level
    if paternal_gp or maternal_gp:
        print("\n  GRANDPARENTS:")
        line = "  "
        boxes = []
        if paternal_gp:
            gp_str = " ═══ ".join([f"[{n}]" for n in paternal_gp])
            boxes.append(gp_str)
        if maternal_gp:
            gp_str = " ═══ ".join([f"[{n}]" for n in maternal_gp])
            boxes.append(gp_str)
        print(line + "              ".join(boxes))

        # Connection lines
        print("         │                              │")
        print("         ▼                              ▼")

    # Parents level with aunts/uncles
    print("\n  PARENTS & AUNTS/UNCLES:")

    # Get aunts/uncles for each side
    paternal_siblings = tree.get_siblings(couple['father'])
    maternal_siblings = tree.get_siblings(couple['mother'])

    parent_line = "  "
    if paternal_siblings:
        parent_line += " ".join([f"({n})" for n in paternal_siblings]) + "  "
    parent_line += f"┌─[{couple['father']}]═══════[{couple['mother']}]─┐"
    if maternal_siblings:
        parent_line += "  " + " ".join([f"({n})" for n in maternal_siblings])
    print(parent_line)

    # Show cousins if any
    cousins = tree.get_cousins(user_name)
    if cousins:
        print("  " + " " * 20 + "│           │")
        cousin_line = "  Cousins: " + ", ".join(cousins)
        print(cousin_line)

    # Connection to children
    print("  " + " " * 20 + "│           │")
    print("  " + " " * 20 + "└─────┬─────┘")
    print("  " + " " * 26 + "│")
    print("  " + " " * 26 + "▼")

    # User and siblings level
    print("\n  YOU & SIBLINGS:")
    siblings = tree.get_siblings(user_name)
    user_person = tree.members[user_name]

    user_box = f"★[{user_name}]★"
    if user_person['spouse']:
        user_box += f"═══[{user_person['spouse']}]"

    sibling_boxes = []
    for sib in siblings:
        sib_person = tree.members[sib]
        sib_box = f"[{sib}]"
        if sib_person['spouse']:
            sib_box += f"═[{sib_person['spouse']}]"
        sibling_boxes.append(sib_box)

    all_boxes = [user_box] + sibling_boxes
    print("  " + "    ".join(all_boxes))

    # Children level
    user_children = user_person['children']
    sibling_children = []
    for sib in siblings:
        sib_person = tree.members[sib]
        for child in sib_person['children']:
            sibling_children.append((sib, child))

    if user_children or sibling_children:
        print("  " + " " * 5 + "│")
        print("  " + " " * 5 + "▼")
        print("\n  CHILDREN (Your descendants):")

        if user_children:
            child_boxes = []
            for child in user_children:
                child_person = tree.members[child]
                child_box = f"[{child}]"
                if child_person['spouse']:
                    child_box += f"═[{child_person['spouse']}]"
                child_boxes.append(child_box)
            print("  " + "  ".join(child_boxes))

            # Grandchildren
            grandchildren = []
            for child in user_children:
                child_person = tree.members[child]
                for gc in child_person['children']:
                    grandchildren.append((child, gc))

            if grandchildren:
                print("  " + " " * 5 + "│")
                print("  " + " " * 5 + "▼")
                print("\n  GRANDCHILDREN:")
                for parent, gc in grandchildren:
                    gc_person = tree.members[gc]
                    gc_box = f"[{gc}]"
                    if gc_person['spouse']:
                        gc_box += f"═[{gc_person['spouse']}]"
                    print(f"    {gc_box} (child of {parent})")

    # Legend
    print("\n  " + "─" * 50)
    print("  LEGEND:")
    print("    ★[Name]★  = You (the user)")
    print("    [Name]    = Family member")
    print("    (Name)    = Aunt/Uncle")
    print("    ═══       = Married/Spouse")
    print("    │ ▼       = Parent-Child relationship")
    print("  " + "─" * 50)

    # Print raw variables
    print("\n--- Raw Variables ---")
    print(f"user_name = {repr(user_name)}")
    print(f"couple = {couple}")
    print(f"\nfamily_tree.members = {{")
    for name, data in tree.members.items():
        print(f"  {repr(name)}: {{")
        print(f"    'spouse': {repr(data['spouse'])},")
        print(f"    'children': {data['children']},")
        print(f"    'parents': {data['parents']}")
        print(f"  }},")
    print("}")


def main():
    """Main function to run the family tree program."""
    tree = FamilyTree()

    # Get user and parents info
    user_name = get_user_info(tree)

    print(f"\nHello {user_name}!")
    print(f"Your parents are {tree.couple['father']} (father) and {tree.couple['mother']} (mother).")

    # Ask if user wants to add more family members
    add_more = input("\nWould you like to add more family members? (yes/no): ").strip().lower()
    if add_more in ('yes', 'y'):
        add_family_members(tree)

    # Print the family tree
    print_family_tree(tree)


if __name__ == "__main__":
    main()
