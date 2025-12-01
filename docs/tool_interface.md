This document explains the following:

- **What should be the inputs**
- **What the tool assumes re the SMV model**
- **What are the allowed actions and what is forbidden in the model**
- **What should appear in the `factors.json` file**
- **What are the outputs**

## 1. What does the tool do?

Given:

- An SMV model
- Factors specification - Each factor represents **one logical property of the system**. The factor can take **several possible values**. They are the basic building blocks of CTD.

The tool:

1. Generates a **pairwise (CTD) designed test** out of the factors.
2. It uses the **LTL properties** that are built out from the template and **nuXmv** as the oracle in order to:
    - Deciding which **rows** of all the factors are **feasible/ infeasible**
    - Deciding which **pairs** of factor values are **feasible/ infeasible**
    - making sure that **all feasible pairs** are one of the following options:
        - proven that they are infeasible, or
        - are covered by at least one feasible row.

The final result is:

- A **test suite** that is built of feasible rows.
- Clasiffying pairs into the following groups:
    - **feasible**
    - **infesible**
    - **covered** - feasible and appear in at least one test
    - **Test Steps (ST)** for each feasible test which are nuXmv traces.

## 2. Inputs

### 2.1 Input Files:

1. `model.smv` - the nuXmv model of the system under test.
2. `factors.json` - a JSON configuration that describes:
    - the logical properties that are treated as **factors**
    - The **values** they can have
    - how to use these factors in **LTL formulas**

## 3. Requirements on `model.smv`

### **must** exist in the model:

    1. **a valid SMV/nuXmv model**

    2. A **step variable** for example: 
        ```smv
        VAR
        step : {login, logout, add, remove, checkout, idle};
        ```
    The name of the variable is given in the `factors.json` under `step_var`. it uses this for the test steps (ST).

    3. An **end-of-the-test flag** for example:
        ```smv
        VAR
        end_of_test : boolean;
        ```
    The name of the variable is given in the `factors.json` under `end_flag`. It becomes TRUE when the scenario is considered as "completed" for the LTL formula `F(end_of_test & {conditions})`

    4. **State variables that match the predicates of the factors**
    - For each factor there are the values of it in the SMV model for example:
        - `a_no_logout_after_add` - a boolean state variable.
        - `b_max_items`           - an integer variable (`max_items`).
        - `c_no_remove`           - a boolean variable (`removed_ever` etc., via a condition).
    - The mapping is being done in the LTL template

## 4. Structure and Semantics - `factors.json`
The file describes which properties participate in CTD and how they are encoded in LTL.
Right now values can be of two types - Boolean and integers. 
The tool builds a conjunction of the factor values for example:
    `ltl_template = "F(end_of_test & {conditions})"` - meaning - there exists a run that eventually reaches the end of the test and at this point the conditions on the factors hold. This is the template used in all examples and experiments
    The overall property is **monotone** in each factor.

## 5. Outputs
    1. The tool returns four objects:
    
        1. `test_suite`
        - A list of feasible CTD rows
        - Each row has a mappings of the chosen values of the factors.
        - These are the rows that fit a specific LTL formula.

        2. `feasible_pairs`
        - a set of pairs that were proven as stifiable.

        3. `infeasible_pairs`
        - a set of pairs that were proven as impossible - no behavior of the model canhave them     simultaneously.

        4. `covered_pairs`
        - A subset of `feasible_pairs`. Each one appears at least in one row of the test suites.

    2. There are also some external files that the tool produces:

        1. **Test rows file** - one for each row with the factor names and the chosen values.
        2. **Pairs report**  - Feasible or Infeasible
        3. **Test Steps (ST)** - for each feasible test row - the tool uses nuXmv and saves the result in a file as:  
            `run_A0_B3_C1.txt
            run_A1_B4_C0.txt
            ...`
        
        Where each name of the file is combined of the values - in the file of A0_B3_C1 it means A value is False, B value is 3 and C value is 3.
        4. **Summary log** - How many tests, how many pairs are feasible or infeasible and the coverage status.