# Scripted Test (auto-generated from nuXmv trace)

## Given

- System starts in **LoggedOut**.


## When / Then

**Step 1 – Login**
- Transition: `LoggedOut → Shopping`
- Items: `0 → None`
- Post: a=None, b=None, c=None, max_items=None, logout_count=None

**Step 2 – AddItem**
- Transition: `Shopping → None`
- Items: `None → 1`
- Post: a=None, b=None, c=None, max_items=1, logout_count=None

**Step 3 – Checkout**
- Transition: `None → CheckedOut`
- Items: `5 → 0`
- Post: a=None, b=None, c=None, max_items=None, logout_count=None

**Step 4 – AddItem**
- Transition: `Shopping → None`
- Items: `None → 1`
- Post: a=None, b=None, c=None, max_items=None, logout_count=None

**Step 5 – RemoveItem**
- Transition: `None → None`
- Items: `3 → 2`
- Post: a=None, b=None, c=False, max_items=None, logout_count=None

**Step 6 – AddItem**
- Transition: `None → None`
- Items: `2 → 3`
- Post: a=None, b=None, c=None, max_items=None, logout_count=None

**Step 7 – RemoveItem**
- Transition: `None → None`
- Items: `3 → 2`
- Post: a=None, b=None, c=None, max_items=None, logout_count=None
