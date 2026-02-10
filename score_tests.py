import sys
from pathlib import Path

BUGS = [
    {
        "id": "Bug 1",
        "name": "Double checkout",
    },
    {
        "id": "Bug 2",
        "name": "Logout after checkout",
    },
    {
        "id": "Bug 3",
        "name": "Long mixed shopping",
    },
    {
        "id": "Bug 4",
        "name": "Checkout with two items",
    },
]

ALLOWED_ACTIONS = {"login", "logout", "add", "remove", "checkout"}

def parse_test_suite(path: Path):
    """
    Reads a test suite file and returns a list of tests.
    Each test is a list of action strings.
    """
    if not path.exists():
        raise FileNotFoundError(f"Test suite file not found: {path}")

    tests = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                # ignore empty lines
                continue

            # split by comma and strip spaces
            actions = [tok.strip() for tok in line.split(",") if tok.strip()]

            # (optional) basic validation: only allowed actions
            for a in actions:
                if a not in ALLOWED_ACTIONS:
                    raise ValueError(
                        f"Invalid action '{a}' on line {lineno} in {path}"
                    )

            tests.append((lineno, actions))

    return tests

def detect_bugs(tests):
    """
    Detects planted bugs in the given tests.
    Input:
      tests: list of (lineno, actions_list)
    Output:
      dict: bug_id -> list of line numbers that triggered this bug
    """
    # Initialize result dictionary: each bug id -> empty list of lines
    results = {bug["id"]: [] for bug in BUGS}

    for lineno, actions in tests:
        # ---------------------------------
        # Bug 1 – Double checkout 
        # ---------------------------------
        if "Bug 1" in results:
            checkout_indices = [i for i, a in enumerate(actions) if a == "checkout"]
            if len(checkout_indices) >= 2:
                first_checkout_idx = checkout_indices[0]
                has_add_before_first_checkout = any(
                    a == "add" for a in actions[:first_checkout_idx]
                )
                if has_add_before_first_checkout:
                    results["Bug 1"].append(lineno)

        # ---------------------------------
        # Bug 2 – Logout after checkout
        # ---------------------------------
        if "Bug 2" in results:
            checkout_indices = [i for i, a in enumerate(actions) if a == "checkout"]
            logout_indices = [i for i, a in enumerate(actions) if a == "logout"]
            if checkout_indices and logout_indices:
                has_checkout_before_logout = any(
                    ci < li for ci in checkout_indices for li in logout_indices
                )
                if has_checkout_before_logout:
                    results["Bug 2"].append(lineno)

        # ---------------------------------
        # Bug 3 – Long mixed shopping 
        # Prefix before first checkout has:
        #   - length >= 6
        #   - at least 2 adds
        #   - at least 1 remove
        #   - cart non-empty at first checkout (items > 0)
        # ---------------------------------
        if "Bug 3" in results and "checkout" in actions:
            first_checkout_idx = actions.index("checkout")
            prefix = actions[:first_checkout_idx]

            if len(prefix) >= 6:
                add_count = prefix.count("add")
                remove_count = prefix.count("remove")

                if add_count >= 2 and remove_count >= 1:
                    # Simulate items counter up to the first checkout
                    items = 0
                    for a in prefix:
                        if a == "add" and items < 5:
                            items += 1
                        elif a == "remove" and items > 0:
                            items -= 1
                    if items > 0:
                        results["Bug 3"].append(lineno)

        # ---------------------------------
        # Bug 4 – Checkout with two items
        # At any checkout in the test, items == 2 at that point
        # ---------------------------------
        if "Bug 4" in results:
            items = 0
            triggered_bug4 = False
            for a in actions:
                if a == "add" and items < 5:
                    items += 1
                elif a == "remove" and items > 0:
                    items -= 1

                if a == "checkout" and items == 2:
                    triggered_bug4 = True
                    break

            if triggered_bug4:
                results["Bug 4"].append(lineno)

    return results




def main():
    if len(sys.argv) != 2:
        print("Usage: python score_tests.py <test_suite_file>")
        sys.exit(1)

    suite_path = Path(sys.argv[1])

    try:
        tests = parse_test_suite(suite_path)
    except Exception as e:
        print(f"Error while reading test suite: {e}")
        sys.exit(1)

    print(f"Loaded {len(tests)} tests from {suite_path}")
    for lineno, actions in tests:
        print(f"  line {lineno}: {actions}")

    # Step 1: call bug detection
    bug_hits = detect_bugs(tests)

    # Compute score
    total_bugs = len(BUGS)
    detected_bug_ids = [bug_id for bug_id, lines in bug_hits.items() if lines]
    detected_count = len(detected_bug_ids)

    print("\n--- Scoring summary ---")
    print(f"Score: {detected_count} / {total_bugs}\n")

    print("Detected bugs:")
    if not detected_bug_ids:
        print("  (none)")
    else:
        for bug in BUGS:
            bid = bug["id"]
            lines = bug_hits.get(bid, [])
            if lines:
                print(f"  - {bid} – {bug['name']}")
                print(f"      triggered by test lines: {', '.join(map(str, lines))}")

    print("\nMissed bugs:")
    for bug in BUGS:
        if bug["id"] not in detected_bug_ids:
            print(f"  - {bug['id']} – {bug['name']}")

if __name__ == "__main__":
    main()
