#CTD-TLP Tool
the following is a small research tool that connects three things:

- CTD - **Combinatorial Test Design** builds a *small set of configurations* over abstract factors (for example - a pairwise).
- TLP - **Temporal Logic Properties** of a system in LTL properties - each value (of the factor) is mapped to a temporal property of the model.
- A nuXmv model - Which is a symbolic model tool that acts as an **oracle**: for each row. It answers whether the row is **feasible** and if so it produces an ST - the test steps.

Our example is a **shopping cart** model with three temporal predicates:

- `a_no_logout_after_add` - Was (not) there a logout after the first add? 
- `b_max_items` - the maximum number of items that was ever reached in the cart
- `c_no_remove` - Was there a remove made in the cart?

Everything is organized in a way that allows one to reuse the same flow with different `factors.json` and a different SMV model.

## Model Contract (`model.smv`)
Any SMV model used with this tool must have some basic identifiers (as described down here). In these conditions the generator and the oracle can run any model without being aware to its details.

### Must have variables (in the `VAR` block)

- `mode` - an abstract mode of the system e.g. - loggedOut, Shopping, CheckedOut

- `step` - The last abstract step that was taken such as login, add, remove, checkout, idle. They are used by the CTD workflow and the oracle.

- `end_of_test` - It is a boolean flag that becomes TRUE when the ST reached the final step. The model stops when it is TRUE.

if any of these are absent from the `VAR` block the model will fail with an error message regarding it.

### CTD predicates - The TLP "atoms"
Each factor in `factors.json` has a predicate (Boolean or numeric) that represents a specific temporal property that should or should not occur. They are defined in the SMV model:

- `a_no_logout_after_add`
- `b_max_items` 
- `c_no_remove` 

## Configuration

The configuration is used in the tool:

From a `factors.json` file - examples or experiments

it lists each factor, its type, and its possible values. For example:
`[
    { "name": "a_no_logout_after_add",  "kind": "boolean"                       },
    { "name": "b_max_items",            "kind": "integer",  "values": [3,4,5]   },
    { "name": "c_no_remove",            "kind": "boolean"                       }
]
It is assumed that the values for Boolean are [FALSE, TRUE] if they are not given.

You run the tool with:
`python -m tool.cli generate --factors factors.json --pairwise`

The goal: to describe the **factors** (names, types, allowed values) and how they map to the predicates in the model.

