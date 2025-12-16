The script finds a small set of feasible tests based on CTD algorithm (pairwise) while using the nuXmv model as the oracle.  
It generates LTL formula for each selected pair, by combining the factor LTL formulas which are defined in `factors.json`.  
The LTL formula is used to ask the nuXmv if a feasible trace exists which satisfies the two factor conditions.

## How the tool is working

### 1. Inputs

The tool reads two files: `factors.json` and `model.smv`

- `factors.json` – defines the test parameters of the system which is under test. It includes their domains and the temporal constraints for each parameter's value. The LTL formulas are constructed from the factors.  
- `model.smv` – The set of rules that exist in our testing system.

### 1.1 Termination and Summary Variables
- In the SMV model exists a termination flag names `end_flag` that signifies the termination of a test execution process. The tool consideres only execution traces that reach the state where end_flag = TRUE.
 
- The model intruduces summary state variables that store information over the execution and are only used to retrieve the final values of the factors. 
For instance, summary variables can track whether there was a logout following an add operation or the maximum number of items added during a run.  

### 1.2 Factor Domain Enforcement
When factors have non-Boolean domains such as integers, the enforcement of the domain in the oracle query is made explicit.

In the final state of the execution, the SMV variable corresponding to the above-mentioned factor will be constrained to be equal to one of the values declared in `factors.json`.

For example a factor with the domain of {3,4,5}, the oracle call is made with the following constraint:
  '(b_max_items = 3) ∨ (b_max_items = 4) ∨ (b_max_items =5)`

This is to ensure that the oracle does not return trails whose final values satisfy the ones mentioned in the `model.smv` for example for max_items it might be {0,..,5}.


- Each **factor** represents a testing dimension (i.e. an abstract test parameter).
The temporal meaning of each factor is defined in `factors.json` using one or more LTL formulas, where more than one formula is used when a single factor value imposes a few temporal constrains (an integer value of a factor).  
Together These formulas give a description of the required temporal property for every possible factor value.

Values which are in the domain of a single factor are considered mutually exclusive by their definition, it is enforced by construction - each test case assigns exactly one value per factor, whereas the values of different factors are cosidered mutually exclusive only if the system's constraints is infeasible with the values of the specific factors. 

In the SMV model the summary state variables are implemented in a way where  
they reflect all the steps that were done during the entire run up until `end_flag = TRUE`.  
For example – wether "no logout after add" had ever occured, or what the maximum items number was.  
The summary state variables are used only to extract the final factor values after a feasible trace was found.

**What are the factors**

The LTL formula that is passed for each test has the structure defined in `factors.json`.  
It is constructed directly from the per-factor LTL formula.  

For a given factor-value assignment `(f = v)`, the matching LTL formula `phi_f(v)` is taken from `factors.json`.  
When a pair is selected `(f1 = v1, f2 = v2)`, the tool constructs:

`phi = F (phi_f1_(v1) & phi_f2(v2))`


Which means that the temporal aspect is encoded in the SMV transition relation.  
The LTL checks whether there exists a trace which satisfies the LTL formulas according to the factor values that were chosen.  
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
   - construct the LTL formula  
     ```
     phi = F (phi_u(x) & phi_v(y))
     ```
     `phi_u(x)` and `phi_v(y)` are taken from `factors.json` (LTL formulas).

2. Ask nuXmv oracle if there is an execution  trace in the FSM that satisfies `phi`  
   (implemented by checking `!(phi)`; the nuXmv returns a counterexample  
   that satisfies `(phi)` if it is feasible or None if there is no such trace)

   1. If no such trace exists – the pair `(u=x, v=y)` will be marked as infeasible and will be removed from the list **todo**.
   2. If such a trace exists –
      1. Let `W = <s_0, s_1,..., s_k>` be the execution trace that is returned by the nuXmv oracle, where every `s_i` is a system state.   
         Save `W` as a trace file in the `output_traces` folder.
     2. Let `t = s_k` be the final state of `W`.  
     This state represents the entire assignment of values to factors through the summary variables.(specifically for factors that are different from `(x, y)`).  
      3. Extract the full CTD row from the summary variables in state `t`.
      4. For each remaining pair in **todo**, check whether its factor values hold in state `t`.
      5. Remove from **todo** all the pairs satisfied by `t`.

---

### 4. Test Minimization

At the end of the process the tool minimizes the amֹount of generated test vectors.  
This is operated without invoking the nuXmv oracle – Tests whose covered pairs are entirely subsumed by any other test(s) are removed,  
while maintaining full feasible pairwise coverage. 

**The pseudo code**:
```
For each test t:
  compute Covered(t) = { feasible pairs satisfied by t }

Remaining = all feasible pairs
Selected != 0

while Remaining != 0
  choose test t with maximum |Covered(t) ∩ Remaining|
  Selected = Selected ∪ {t}
  Remaining = Remaining \ Covered(t)

return Selected  
```
---

At the end the algorithm creates the `output_traces` folder which contains one trace per generated test.  
Every trace satisfies a conjunction of specific factors LTL fomulas.  
The final state of every trace is used to extract the complete assignment of factor values for this specific test.

Together, all the tests cover all the feasible CTD pairs.  
Naturally we hope to have as few tests (and trace files) as possible.

---

## Assumptions

The smv model **must** provide the following:

- `end_flag` (`end_of_test`) which becomes TRUE when the test is completed.
  - The tool enforces its completion by conjoining `F(end_flag)` to every oracle query,
    so that each returned trace reaches `end_flag = TRUE`.

- summary variables for all factors – which suit the factors' extracted variables that the `smv_var` resolves to.
  - one SMV variable per factor (or for few values if the factor is an integer)
  - the variables accumulate information over the entire run - for example - `max_items` and `removed_ever`
  - Their values in the final `end_flag = TRUE` state represent the factor values of the test

The model **may** include:

-Additional state variables in the model.smv, which are not referenced in factors.json

The model **must not** include:
