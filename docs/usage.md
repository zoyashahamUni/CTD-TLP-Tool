# Usage

## Requirements
- macOS with nuXmv installed (your binaries are one folder above this repo)
- Terminal

## Quick run
This model checks the following LTL property: !F ( (b_target = 3) & mode = CheckedOut & a_no_logout_after_add & b_max_items & c_no_remove ).

If nuXmv produces a counterexample it means that the positive form of the property (the expression inside the !) has a valid execution path - the scenario we're testing can actually occur and this is one example for it.

If there is no counter example, it means that the negated form (!F...) is true, so the original property (without the !) cannot occur - it is not a valid or reachable test scenario.

**example**: run nuXmv on the main shopping-cart model and have it saved to a file called trace_output.txt. 

From the repo root:
```
nuXmv -int shoppingCart291025.smv
read_model -i shoppingCart291025.smv
flatten_hierarchy
encode_variables
build_model
go
check_ltlspec -p "F ( (b_target = 3) & mode = CheckedOut & a_no_logout_after_add & b_max_items & c_no_remove )"
show_traces -a -v -o trace_output.txt
quit

grep -E "^\s*-> State:|^\s*mode\s*=|^\s*step\s*=" trace_output.txt | nl -ba
```
Make sure (for example with ls -ltr) what's the name of the file that was actually saved, as sometimes it might be saved as "1_trace_output.txt" or something of this kind. 
cat <<EOF
