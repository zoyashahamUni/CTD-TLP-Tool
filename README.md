# CTD-TLP Tool
This is a small research tool that connects three components:

- CTD - **Combinatorial Test Design** builds a *small set of configurations* over abstract factors (e.g., a pairwise set) in an IPO style manner.
- TLP - **Temporal Logic Properties** of a system in LTL properties - each factor value maps to an LTL temporal property of the model.
- A nuXmv model - Which is a symbolic model tool that acts as an **oracle**: for each row it answers whether the row is **feasible** and if so it produces an ST - the test steps.

Our running example is a **shopping cart** model with three temporal predicates:

- `a_no_logout_after_add` - Was (not) there a logout after the first add.
- `b_max_items` - the maximum number of items ever reached in the cart
- `c_no_remove` - Was there a remove made in the cart.

Everything is organized in a way that allows one to reuse the same flow with different `factors.json` and a different SMV model.

## Model Contract (`model.smv`)
Any SMV model used with this tool must have some basic identifiers (as described down here). In these conditions the generator and the oracle can run any model without being aware to its details.

### Must-have variables (in the `VAR` block)

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

The configuration reads its configuration from `factors.json` - it lists the name, its type (boolean or integer), and its possible values. For example:
`[
    { "name": "a_no_logout_after_add",  "kind": "boolean"                       },
    { "name": "b_max_items",            "kind": "integer",  "values": [3,4,5]   },
    { "name": "c_no_remove",            "kind": "boolean"                       }
]`
It is assumed that the values for Boolean are [FALSE, TRUE] if they are not given.

You run the tool with:
`python -m tool.cli generate --factors factors.json --pairwise`

The goal: to describe the **factors** (names, types, allowed values) and how they map to the temporal predicates in the model.

## CTD Generation (`generate` command)

The `generate` command checks factors.json and derives: 
- all the names of the factors
- the normalized domains
- pairwise rows.
- The LTL formulas for each row 

### Printing the normalized domains:###

`python -m tool.cli generate --factors factors.json --print-rows`

### Generating pairwise rows###
The tool uses an IPO based algorithm to produce the minimal possible pairwise set of covering rows:

`python -m tool.cli generate --factors factors.json --pairwise`

An example output is:
[ctd-tlp-tool] Twix pairwise rows: 6
  01. a_no_logout_after_add=FALSE, b_max_items=3, c_no_remove=FALSE
  02. a_no_logout_after_add=FALSE, b_max_items=4, c_no_remove=TRUE
  ...

### Generating LTL formulas for each row ###
Using the ltl_template in the JSON file:

`python -m tool.cli generate --factors factors.json --pairwise --ltl`

Every row is becoming a temporal requirement phi that looks like:

`F(end_of_test & a_no_logout_after_add & b_max_items=3 & !c_no_remove)`

## Running the Oracle ##
This is the core of this tool. it combines the following:
- **CTD** - generates pairwise rows.
- **LTL Properties** - A single temporal requirement per row.
- **nuXmv** - produces the suggested test steps (ST) and checks whether the row is feasible. 

The following command runs the dynsmic IPO algorithm: It generates pairwise rows, calls the nuXmv to analyze each row if feasible/ infeasible and checks which is the infeasible pair on the specific row.

`python -m tool.cli oracle-ipo \
    --model examples/shopping/model.smv \
    --factors examples/shopping/factors.json \
    --output-dir output_ipo`

# How the Oracle Works
The oracle is built in two phases:

# Phase 1 - Pairwise Rows - Feasibility and Infeasibility Pair Detection#
The tool generates pairwise rows and instantly checks each row with the oracle. If it's a feasible row - then it contributes to the coverage, otherwise it means that the row is infeasible and a check is triggered to find the first infeasible pair on this row.
1. Have the two values one for A and the second for B
2. Maximizing pairwise coverage by choosing a value for C.
3. Call nuXmv
4. Classify the row as:
    - **Feasible** - The model produces a counterexample to !phi.
    - **Infeasible** - No test steps that can satisfy this row.
This first phase most often covers the pairs majority.
In addition, if a row is infeasible, Phase 1 identifies the first infeasible pair so later phases avoid generating impossible configurations.

# Phase 2 - Completing the Coverage #
Following the first phase the tool computes which pairs are still uncovered (excluding pairs already proven infeasible) and tries to cover them in an oracle guided way:

- Identifying all the pairs that are not marked as covered nor proven infeasible.
- selecting one uncovered pair as the next target.
- Try to build a row containing this pair while avoiding all known infeasible pairs.
- If no such row can be built it means that the pair is infeasible.
- If the row is built:
    - call nuXmv on the row
    - If feasible - mark all its pairs as feasible and covered. 
    - If infeasible - find the first infeasible pair in the row using the pair-level oracle.
All this continues until every feasible pair is covered by at least one feasible row, and every impossible pair is explicitly marked as infeasible.

## How the Feasibility is Determined ##
1. The tool builds an LTL formula (F) phi for each row. E.g:
`F(end_of_test & a_no_logout_after_add & (b_max_items = 3) & !c_no_remove)`
2. To check the Line's feasibility:
    - the tool negates the formula to !phi
    - It asks the nuXmv if the !phi holds:
        - if !phi is FALSE - a counter example is produced in terms of **test steps** (ST).
        -if !phi is TRUE it means there is no counterexample, so no test steps that exist which means that this phi is infeasible.  

In addition, when a row is infeasible, the oracle performs pair-level feasibility checks. For each 2-way pair inside the row, it constructs a partial temporal requirement and tests it with nuXmv. If a pair has no valid completion in the model, it is marked as an **infeasible pair**. If a pair is satisfiable, it is marked as **feasible**, but it is considered **covered** only when it appears in a feasible full row that produces an ST trace.

## The Output Directory ##
After running the `oracle_ipo`, the output directory will look like:
   `output_ipo/
    run_A0_B3_C0.txt
    run_A0_B4_C1.txt
    run_A0_B5_C0.txt
    run_A1_B3_C1.txt
    run_A1_B4_C0.txt
    run_A1_B5_C1.txt
    feasible.txt
    infeasible.txt`

**Trace Files (`run_A*_B*_C*.txt`)**
Every feasible row has a file that contains:
- All visited states
- All `test steps`
- The values of the CTD predicates 
- The indication of end_of_test = TRUE

**feasibile.txt**
The list of all the profiles that the model satisfied.

**infeasible.txt**
The list of all the profiles that the model cannot satisfy.
Note that infeasible profiles do not produce ST files, and their 2-way pairs are analyzed individually to discover which pairs are impossible in the model.


## Example Output ##
The following matches the expected pairwise coverage for A,B,C:
`Feasible profiles: 6
Infeasible profiles: 0
Profiles:
  A0_B3_C0
  A0_B4_C1
  A0_B5_C0
  A1_B3_C1
  A1_B4_C0
  A1_B5_C1`

Since no infeasible profiles were found, all 2-way pairs in the factor space were covered by at least one feasible row, each producing an ST trace.


### End-to-End Example - The Shopping Cart Model ###
The example describes a small shopping cart system that has three temporal predicates that define the test space:
    - a_no_logout_after_add
    - b_max_items
    -c_no_remove

The workflow uses the example model and the factors that are supplied in `examples/shopping/`:
    - factors.json
    - model.smv

1. **Define the Factors**
`examples/shopping/actors.json`:
    `[
        { "name": "a_no_logout_after_add", "kind": "boolean" },
        { "name": "b_max_items",           "kind": "integer", "values": [3, 4, 5] },
        { "name": "c_no_remove",           "kind": "boolean" }
    ]`
The domain is based on:
    A {TRUE, FALSE}
    B {3, 4, 5}
    C {TRUE, FALSE}

2. **Generating Pairwise Rows**
    `python -m tool.cli generate \
    --factors examples/shopping/factors.json \
    --pairwise`

The example for the output that gives full pairwise coverage of the A, B, C factors:
    `[ctd-tlp-tool] Twix pairwise rows: 6
  01. a_no_logout_after_add=FALSE, b_max_items=3, c_no_remove=FALSE
  02. a_no_logout_after_add=FALSE, b_max_items=4, c_no_remove=TRUE
  03. a_no_logout_after_add=FALSE, b_max_items=5, c_no_remove=FALSE
  04. a_no_logout_after_add=TRUE,  b_max_items=3, c_no_remove=TRUE
  05. a_no_logout_after_add=TRUE,  b_max_items=4, c_no_remove=FALSE
  06. a_no_logout_after_add=TRUE,  b_max_items=5, c_no_remove=TRUE`

3. **Generating LTL Specification for Each Row**
Each row turns into a temporal requirement that holds on the final state:
    `python -m tool.cli generate \ --factors examples shopping/factors.json \ --pairwise --ltl 

The output is:
    `Row 01: {'a_no_logout_after_add': False, 'b_max_items': 3, 'c_no_remove': False}
  LTL: F(end_of_test & !a_no_logout_after_add & (b_max_items = 3) & !c_no_remove)

4. **Running the Oracle**
python -m tool.cli oracle-ipo \ --model   examples/shopping/model.smv \ --factors examples/shopping/factors.json \ --output-dir output_ipo

In this case the model can satisfy the following temporal combinations:
`[ctd-tlp-tool] IPO completed.
  Feasible profiles : 6
  Infeasible profiles: 0
  Feasible list:
    - A0_B3_C0
    - A0_B4_C1
    - A0_B5_C0
    - A1_B3_C1
    - A1_B4_C0
    - A1_B5_C1`

5. **Viewing the Results**
The output files are saved in `output_ipo/`:
    `output_ipo/
    run_A0_B3_C0.txt
    run_A0_B4_C1.txt
    run_A0_B5_C0.txt
    run_A1_B3_C1.txt
    run_A1_B4_C0.txt
    run_A1_B5_C1.txt
    feasible.txt
    infeasible.txt`

6. **Collecting the test steps (ST)**
The following are suggested **test steps** (ST) to achieve the temporal properties for that specific row: 
    `Trace Description: LTL Counterexample
    Trace Type: Counterexample
      -> State: 1.1 <-
        mode = LoggedOut
        items = 0
        step = login
        ...
      -> State: 1.2 <-
        mode = Shopping
        step = add
        items = 0
      -> State: 1.3 <-
        items = 1
        ...
      -> State: 1.7 <-
        end_of_test = TRUE`

### The Output Files ###

The Oracle produces a directory called `output_ipo/` that contains all the feasible, infeasible and the suggested test steps (STs).
The folder usually looks like:
    `run_A0_B3_C0.txt
    run_A0_B4_C1.txt
    run_A0_B5_C0.txt
    run_A1_B3_C1.txt
    run_A1_B4_C0.txt
    run_A1_B5_C1.txt
    feasible.txt
    infeasible.txt`

the roles of the files are as follows:

1. **Test Steps (ST) Files - run_A*_B*_C*.txt**
for every row that the model satisfies, the oracle generates a suggested test file called for example: `run_A1_B3_C0.txt`

**The Name A1_B3_C0 means:**
- a_no_logout_after_add = TRUE  - A1
- b_max_items           = 3     - B3
- c_no_remove           = FALSE - C0

The profile name uses: 
- The first letter of each factor's name.
- The value of the factor, with the boolean converted to 0,1.

**The content of each file (the test steps of the suggested test):**
    `Trace Description: LTL Counterexample
    Trace Type: Counterexample
      -> State: 1.1 <-
        mode = LoggedOut
        items = 0
        step = login
        ...
      -> State: 1.2 <-
        mode = Shopping
        step = add
        items = 0
      -> State: 1.3 <-
        items = 1
        ...
      -> State: 1.7 <-
        end_of_test = TRUE`

2. **`feasible.txt**
The list of all the profiles that the model satisfies, for example:
    `A0_B3_C0
    A0_B4_C1
    A0_B5_C0
    A1_B3_C1
    A1_B4_C0
    A1_B5_C1`

- Each line is the profile's name.
- Every profile has a matching run_A*_B*_C*.txt file.

3. **`infeasible.txt`**
The list of all the profiles that the model cannot satisfy, for example:
    `A0_B3_C1
    A1_B4_C1`

- They indicate which CTD combinations are impossible in the system.
- They don't produce a file.

Internally, the tool distinguishes between pairs that are logically feasible (feasible_pairs) and pairs that are actually covered by a feasible full row producing an ST trace (covered_pairs); only covered pairs represent real tests.


### A Note ###
- re-running the tool will overwrite the old `output_ipo/` directory.

## Algorithm Summary (Dynamic IPO–TLP)

The oracle-based algorithm combines combinatorial generation with model-checking:

1. **Phase 1 – Twix Pairwise Rows**
   - Generate the row and test it with nuXmv.
   - Feasible rows produce ST files and contribute their pairs to **feasible_pairs** and **covered_pairs**.
   - Infeasible rows trigger a pair-level oracle that finds the **first infeasible pair** in that row.
   - Feasible pairs found at the pair-level are added to **feasible_pairs**, but only become **covered** when they appear in a feasible full row.

2. **Phase 2 – Dynamic Completion**
   - Identify pairs that are neither covered nor infeasible.
   - For each such pair:
       - Attempt to build a full row avoiding known infeasible pairs.
       - If impossible → the target pair is marked **infeasible**.
       - If a row is built → test it with nuXmv.
           - Feasible → pairs are added to **feasible_pairs** and **covered_pairs**.
           - Infeasible → find the first infeasible pair using the pair-level oracle.

The process stops when:
- Every feasible pair is **covered** (appears in at least one feasible test row with an ST trace).
- Every impossible pair is explicitly marked **infeasible**.

This gets a minimal, oracle-guided CTD test suite with full 2-way coverage over all feasible configurations of the model.
