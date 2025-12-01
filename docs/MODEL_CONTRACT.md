CTD–TLP Tool — SMV Model Contract Specification

This document defines the interface contract that any SMV model must satisfy in order to be used with the CTD–TLP tool.
The contract ensures that the tool can:

Generate LTL properties from CTD factor assignments

Use nuXmv as a feasibility oracle

Extract stable, meaningful test steps (ST)

Perform dynamic IPO coverage with pair-level infeasibility detection

This contract makes the tool model-independent and reusable.

1. Required SMV Variables (in the VAR block)

Every model must contain the following variables with the prescribed semantics.

1.1 mode — Abstract System Mode

Symbolic enumeration describing the system’s high-level state.

Example:

mode : {LoggedOut, Shopping, CheckedOut};


The tool does not assume specific mode values—only that this variable exists.

1.2 step — Last Abstract Action

Represents the last logical action executed, used to interpret nuXmv traces.

Example:

step : {login, logout, add, remove, checkout, idle};


Each transition must select exactly one step value.

1.3 end_of_test — Boolean Termination Flag

Indicates that the test sequence for a row is completed.

Required semantics:

Must become TRUE once the row’s LTL conditions are satisfied

Must remain TRUE afterwards (monotonic)

When end_of_test = TRUE, the model must not continue evolving (i.e., next-state transitions should freeze)

2. CTD–TLP Temporal Predicates (Per-Factor Atoms)

Each factor in factors.json corresponds to a model predicate used in LTL formulas.

Your model must define:

no_logout_after_add (boolean)

max_items (integer)

removed_ever (boolean)

These act as the “semantic observables” used by CTD and the LTL oracle.

3. Required Predicate Behavior

The tool assumes semantic monotonicity and interpretability of predicate values.

The model may be nondeterministic in its internal transitions, as long as these predicates behave consistently.

3.1 no_logout_after_add

Initially TRUE

Becomes FALSE if a logout occurs after at least one add

Must never revert to TRUE

3.2 max_items

Holds the maximum count of items ever reached

Must never decrease

Must evolve deterministically based on item count

3.3 removed_ever

Initially FALSE

Becomes TRUE if any remove occurs

Must never revert to FALSE

4. Allowed Nondeterminism

The SMV model may contain nondeterministic transitions.

However:

❗ The nondeterminism must not violate the meaning of the temporal predicates.

Specifically:

max_items must not arbitrarily decrease

removed_ever must not reset

no_logout_after_add must not flip back to TRUE

end_of_test must remain TRUE once reached

This ensures stable interpretation of ST traces and correct pair-level classification.

5. Required Mapping: Factors → Model Predicates

The CTD-TLP tool translates factor assignments into model-level temporal constraints via LTL.

Factor	Type	Model Predicate	Mapping Rule
a_no_logout_after_add	boolean	no_logout_after_add	TRUE → no logout after add; FALSE → logout occurred
b_max_items	integer	max_items	equality: max_items = N
c_no_remove	boolean	removed_ever	TRUE → removed_ever = FALSE; FALSE → removed_ever = TRUE

This mapping is implemented in ltl_builder.py.

6. Required Termination Behavior

end_of_test must be:

Set to TRUE the moment all conditions of the row’s LTL formula become true

Monotonic

Used to freeze the model (no further transitions)

This ensures nuXmv produces finite, meaningful test traces.

7. Forbidden Model Patterns

The following behaviors violate the contract:

❌ end_of_test toggling back to FALSE

❌ predicates that reset or oscillate

❌ arbitrary nondeterministic changes to max_items

❌ random updates not connected to step or real transitions

❌ continuing transitions after end_of_test = TRUE

❌ meaningless step values or incomplete step enumeration

8. Minimal Compliant Model (Example)
MODULE main

VAR
  mode  : {LoggedOut, Shopping, CheckedOut};
  items : 0..5;
  step  : {login, logout, add, remove, checkout, idle};

  end_of_test : boolean;

  -- CTD-TLP predicates
  no_logout_after_add : boolean;
  removed_ever        : boolean;
  max_items           : 0..5;

ASSIGN
  init(mode)               := LoggedOut;
  init(items)              := 0;
  init(step)               := idle;
  init(end_of_test)        := FALSE;

  init(no_logout_after_add):= TRUE;
  init(removed_ever)       := FALSE;
  init(max_items)          := 0;

  -- Monotonic max_items
  next(max_items) :=
    case
      items > max_items : items;
      TRUE              : max_items;
    esac;

  -- Monotonic remove flag
  next(removed_ever) :=
    case
      step = remove : TRUE;
      TRUE          : removed_ever;
    esac;

  -- One-way violation of logout-after-add
  next(no_logout_after_add) :=
    case
      step = logout & items > 0 : FALSE;
      TRUE                      : no_logout_after_add;
    esac;

  -- Termination
  next(end_of_test) :=
    case
      <LTL conditions satisfied here> : TRUE;
      TRUE                            : end_of_test;
    esac;

9. Model Validation

The tool validates the contract automatically:

python -m tool.cli generate --model model.smv --factors factors.json --print-rows


If variables are missing or invalid, the tool prints an error such as:

Model contract check failed: missing 'end_of_test' in VAR block.

10. Summary

For the CTD–TLP tool to work, an SMV model must:

Define mode, step, and end_of_test

Implement monotonic CTD predicates (no_logout_after_add, max_items, removed_ever)

Allow nondeterminism only if predicate meaning is preserved

Freeze behavior once end_of_test = TRUE

Use logically meaningful step transitions

Support clear mapping between factors and temporal constraints

With this contract, the tool can safely execute dynamic IPO, detect infeasible pairs, and generate usable test steps (STs).