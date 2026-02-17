## How to Run the Demo (Github Codespaces)

### Open the repository
[repository](https://github.com/zoyashahamUni/CTD-TLP-Tool)

### Create your own Codespace

- Click the green **code** button
- Go to the **Codespaces** tab.
- Click **Create codespace on main**.

### Run the example test suite

In the terminal at the bottom of the Codepace site run: 
  `python score_tests.py tests/example_suite.txt`

You will see a score and a list of detected and missed bugs.

### Edit and re-run

- Open `tests/example_suite.txt` in the editor.
- Change or add tests (one test per line, the actions are separated with a commas and followed a space)
- Run again: `python score_tests.py tests/example_suite.txt`
- Watch how the score and the detected bugs list change.

### Run the automatic CTD-TLP generator

In addition to editing a test suite by hand, you can also run the automatic
generator:

```bash
python basic2.py```

The script invokes nuXmv to produce a small set of feasible tests that cover all pairs of the input variables, stores the generated tests as action sequences in the file tests/generated_suite.txt, and finally runs the scoring tool on the file `tests/generated_suite.txt`.

The CTD-TLP generator (`basic2.py`), utilizes the nuXmv model as an oracle to create a compact set of **feasible tests** with pairwise CTD coverage.
It builds complete factor assignments (rows) from pairs of values, evaluates each row with nuXmv using LTL formulas from settings.json, prunes infeasible rows, and marks pairs that cannot occur as **infeasible**, then minimizes the test set while ensuring all feasible pairs are covered.

## How the tool is working

### 1. Inputs

The tool reads two files: `settings.json` and `model.smv`

- `settings.json` – defines the test parameters of the system which is under test. It includes their domains and the temporal constraints for each parameter's value. The LTL formulas are constructed from the factors.
- `model.smv` – The set of rules that exist in our testing system.

### 1.1 Steps and Termination
- A **trace** is a sequence of states returned by the model checker, whereas a **test** is a sequence of actions extracted from that trace.
- As SMV models executions are state sequences only, the action dimension is implicit in the model. In order for the model to encode tests as action sequences, there has to be a designated state variable (it is stated as `step_var` in `settings.json`) which represents the executed action at each state. **The tool extracts the test by collecting values of `step_var` along a trace**.
- `test_rule` is an LTL constraint defining which traces should be treated as valid test traces. In this case `FG(end_flag)`. If `test_rule`is not provided, it is implicitly treated as `TRUE`, and no additional restriction is imposed on the trace.
-`end_flag` indicates the model variable that marks the logical end point of a test and the extraction point for the factors' values.

### 1.2 Test Definition
We view testing as a sequence of actions that a tester sends to a system under test and validates its responses. 
The tool automates the  selection of user actions based on CTD coverage criteria. Verification of the system responses is out of the scope of this tool, assumed to be taken care of by an external mechanism.

The definition of a **test** is model-driven. The user controls this definition with the SMV model and the configuration that is provided in `settings.json`. In particular, the model specifies how action sequences are represented (through the `step_var`) and how the traces should be interpreted as test executions.

Oracle queries need to only be performed on traces satisfying `test_rule`.

LTL formulas are used to characterize properties of traces (tests), not properties of the system under test.

### 1.3 Factor Domain Enforcement
When factors have non-Boolean domains such as integers, the enforcement of the domain in the oracle query is made explicit.

When a factor has a non-Boolean domain  (for example it consists of integers in {3,4,5}) - the oracle query constrains the summary variable at the extraction point, ensuring that factor values are read only from the declared domain. This would mean that its query would include the statement: `(b_max_items = 3) OR (b_max_items = 4) OR (b_max_items = 5)`. This will prevent the oracle from satisfying the pair constraints with any value not in the factor's domain.

- Each **factor** represents a testing dimension (i.e. an abstract test parameter).
The temporal meaning of each factor is defined in `settings.json` using one or more LTL formulas, where more than one formula is used when a single factor value imposes a few temporal constraints (an integer value of a factor).  
Together These formulas give a description of the required temporal property for every possible factor value.

Values which are in the domain of a single factor are considered mutually exclusive by their definition, it is enforced by construction - each test case assigns exactly one value per factor, whereas the values of different factors are considered mutually exclusive only if the system's constraints is infeasible with the values of the specific factors. 

In the SMV model, summary state variables accumulate trace data as it executes, and these would be things such as `removed_ever` and `max_items`. The only purpose of these state variables is to extract factor values in order to define traces and they are not used to control the trace in any way.

Factor values are representing the characteristics of a trace over time, rather than the value of a single state at a specific instant. Although the factors' values are extracted from a designated extraction point (sometimes the last state), their semantics correspond to attributes on the full trace.



**What are the factors**

The LTL formula that is passed for each test has the structure defined in `settings.json`.  
It is constructed directly from the per-factor LTL formula.  

For a given factor-value assignment `(f = v)`, the matching LTL formula `phi_f(v)` is taken from `settings.json`.  
When a full row is selected (i.e., an assignment of one value per factor):
`phi_row = test_rule & phi_f1(v1) & phi_f2(v2) & ... & phi_fk(vk)`

where each `phi_fi(vi)` is the LTL formula for factor `fi` taking value `vi`.

- `test_rule` is an optional LTL constraint taken from `settings.json`
  (for example, it can enforce that the trace eventually reaches the
  logical end-of-test flag). If no `test_rule` is provided, it is treated
  as `TRUE`.
- The per-factor formulas `phi_f(v)` express temporal characteristics that
  may span multiple states, so they are combined directly in conjunction.

The system's temporal behavior is encoded in the SMV transition relation.
Given this model, the oracle query checks whether there exists a trace that
satisfies `phi_row` for the selected factor values.
---

### 2. Pair Generation (**pseudo code**)

The system creates all pairs of the factors' values.  
ALL_PAIRS(factors):
  v = values
  f = factors
  todo = the set of uncovered pairs
  for each (f1, f2) in all 2-combinations of factor names:
    for each v1 in factors[f1].values:
      for each v2 in factors[f2].values:
        add ((f1,v1), (f2,v2)) to todo
  return todo

e.g. – if there are 3 factors:  
`a, b, c`  
`val(a) = {0,1}`, `val(b) = {3,4,5}`, `val(c) = {0,1}`

There will be a full list of all the values of the following factor combinations: `(a,b)`, `(b,c)`, `(a,c)`.

The todo list is:  
`(a.0, b.3), (a.0, b.4) ... (a.0, c.0) ... (b.3, c.0) ... (b.5, c.1)`

### 3. Main Loop

While the todo list is not empty:

1. Pick randomly one pair `(u = x, v = y)` from the list **todo**:

2. **Extend this pair to a full row**:
   - assign `u = x` and `v = y`,
   - for every other factor, assign a default value (the first value in its domain).

3. Construct the LTL formula for the entire row:
   - For each factor-value `(f = v)` in the row, take `phi_f(v)` from `settings.json`.
   - Build
     \[
       \phi_{\text{row}} = \text{test\_rule} \ \&\ \bigwedge_{(f=v)\ \text{in row}} \phi_f(v)
     \]

4. Ask the nuXmv oracle if there is a trace in the SMV model that satisfies
   \(\phi_{\text{row}}\).

   1. **If no such trace exists** (the row is infeasible):
      - Consider all factor pairs appearing in this row.
      - For each such pair, ask nuXmv (via a smaller query) if the pair itself
        is feasible.
      - Pairs that are proven infeasible are added to the `infeasible_pairs`
        set and removed from `todo`.
      - If no pair is infeasible, the row is marked as a higher-order
        infeasibility (3+ factors) and remembered so it will not be tried again.
   2. **If such a trace exists** (the row is feasible):
      - Let \(W = \langle s_0, s_1, \dots, s_k \rangle\) be the returned trace.
      - Extract the test as the sequence of `step_var` values along the trace,
        ignoring `idle` and stopping when `end_flag` becomes `TRUE`.
      - Save the trace in the `output_traces` folder and keep the action
        sequence for this row.
      - Mark all CTD pairs satisfied by the row’s factor assignment as
        covered and remove them from the `todo` list.

---

### 4. Test Minimization

At the end of the process the tool minimizes the amֹount of generated test vectors.  
This is operated without invoking the nuXmv oracle – Tests whose covered pairs are entirely subsumed by any other test(s) are removed,  
while maintaining full feasible pairwise coverage. 

following the greedy minimisation of the tests, `output_traces` folder is pruned to contain only the files corresponding to the selected tests. 

**The pseudo code**:
```
For each test t:
  compute Covered(t) = { feasible pairs satisfied by t }

Remaining = all feasible pairs
Selected ={}

while Remaining != 0
  choose test t with maximum |Covered(t) ∩ Remaining|
  Selected = Selected ∪ {t}
  Remaining = Remaining \ Covered(t)

return Selected  
```
---

At the end the algorithm creates the `output_traces` folder which contains one file per generated test, storing the action sequence (`step_var` values). 
Every trace satisfies a conjunction of specific factors LTL formulas.  
A designated extraction point (sometimes the last state) is used to read the summary variables that characterize the entire trace.

Together, all the tests cover all the feasible CTD pairs.  
Naturally we hope to have as few tests (and trace files) as possible.

---

## Assumptions

The smv model **must** provide the following:

- **Monotonicity Assumption** - Each factor is implemented by a **monotone-increasing** summary state variable (for example for Boolean variables - once it becomes TRUE it never goes back to FALSE), whose final value is semantically equivalent to the factor's LTL definition over the entire trace.
- A step variable whose name is given by `step_var` in `settings.json`. Its values represent the actions executed throughout the test. **It is not enforced by the tool**.

- summary variables for all factors – which suit the factors' extracted variables that the `smv_var` resolves to.
  - one SMV variable per factor (or for few values if the factor is an integer)
  - the variables accumulate information over the entire run - for example - `max_items` and `removed_ever`

The model **may** include:
- A `test_rule` LTL formula (in `settings.json`) that restricts which traces are considered valid tests. If it does not exist then `test_rule = TRUE` - meaning no additional restriction is imposed.


## The Tool's Pseudo Code

INPUT:
SMV model
Factors (domains, temporal definitions and step variable)

INITIALIZE:
Generate all CTD value pairs
Mark all pairs as uncovered

WHILE uncovered pairs is not empty:
Select an uncovered pair (f1=v1, f2=v2)
Build an LTL property that requires this pair holds during a point in the trace
Ask the nuXmv oracle if such a trace exists

IF no:
Mark the pair as infeasible

IF yes:
Get the satisfying trace W
Extract the test as the sequence of test steps
compute the factor values that summarize the trace W
Mark all pairs covered by this test as covered
Store the test steps of this trace.

MINIMIZATION:
Greedily select a small subset of the stored tests so that:
  all feasible pairs are covered

OUTPUT:
Minimized set of tests, each test represents the trace in test steps

###Running the tool in Github Codespaces:

1. Open the repository on the Github site, then click **Code --> Codespace --> Create codespace on main**.
2. Wait for the Codespace to start (VS Code in the browser).
3. Open a Terminal in the Codespase.

You can now run either of the following demos:

- **Manual scorng demo (example suite):**

  ```bash
  python score_tests.py tests/example_suite.txt
  ```

- **Automatic CTD-TLP generator + scoring**
```
python basic2.py
```

There is no local installation required as nuXmv and Python are pre-installed in the Codespace.



  