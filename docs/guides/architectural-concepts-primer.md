# Architectural Concepts Primer

**Audience:** you, reviewing code an LLM wrote for this repository.

This guide is not a Python tutorial. It exists because of a specific problem: an
LLM will produce code that runs, passes the tests you asked for, and is
architecturally wrong in ways that only hurt six months later. You cannot catch
that by reading the diff for bugs. You catch it by having a small number of
principles you apply deliberately, every time.

Each section follows the same four beats:

1. **The idea** — what the concept actually claims.
2. **In this codebase** — where it already lives, with file and line.
3. **Elsewhere** — the same idea in a different domain, so you recognise it out of context.
4. **The review question** — the one thing to ask when an LLM hands you code.

The last two sections are the payoff: a review checklist, and further reading.

Related docs: [the composition navigator](./agent-runtime-composition.html) shows
*where* each construct lives; [the multi-agent design doc](../multi_agent_system.md)
states *what the rules are*. This one explains *why* — the reasoning you need to
extend the rules to a case nobody wrote down.

---

## Table of contents

1. [Module depth: deep vs. shallow](#1-module-depth-deep-vs-shallow)
2. [When a shallow layer earns its keep](#2-when-a-shallow-layer-earns-its-keep)
3. [Data classes as domain models](#3-data-classes-as-domain-models)
4. [Making illegal states unrepresentable](#4-making-illegal-states-unrepresentable)
5. [Partials: turning a constructor into a contract](#5-partials-turning-a-constructor-into-a-contract)
6. [Protocols: contracts without inheritance](#6-protocols-contracts-without-inheritance)
7. [The composition root](#7-the-composition-root)
8. [The dependency rule](#8-the-dependency-rule)
9. [Seams: designing for substitution](#9-seams-designing-for-substitution)
10. [Review checklist for LLM-written code](#10-review-checklist-for-llm-written-code)
11. [Further reading](#11-further-reading)

---

## 1. Module depth: deep vs. shallow

### The idea

This vocabulary comes from John Ousterhout's *A Philosophy of Software Design*.
Picture every module as a rectangle. The **width** is its interface — how much a
caller has to know to use it. The **area** is its functionality — how much work
it does. Depth is area divided by width.

> A **deep module** has a simple interface hiding substantial implementation.
> A **shallow module** has an interface nearly as complicated as what it does.

The claim is not "big modules are good." It's that the *cost* of a module is
its interface, because that's what every caller must carry in their head, and
the *benefit* is its functionality. You want a high benefit-to-cost ratio.

The counterintuitive consequence: **splitting a module in half can make your
system worse.** Two modules with intertwined interfaces cost more than one
module, because now you must understand both interfaces *and* their
relationship. "Classes should be small" is not a principle; it's a heuristic
that frequently produces shallow modules.

Ousterhout's term for the extreme failure is a **classitis** — code sliced so
finely that every class is a thin wrapper and all the real complexity lives in
the wiring between them.

### In this codebase

The deepest module here is
[`create_restaurant_app()`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L192).

Its interface is four values:

```python
app = create_restaurant_app(
    identity=IDENTITY,
    presentation=PRESENTATION,
    graph_adapter_factory=GRAPH_ADAPTER_FACTORY,
    agent_bindings=AgentBindings(...),
)
```

Behind those four values it loads settings from AWS Secrets Manager, builds a
FastAPI app, constructs two WhatsApp clients (async and sync), assembles a
`RestaurantRuntime`, calls the graph factory, registers twelve WhatsApp
handlers with filters, mounts three routers, defines four HTTP routes, and
installs a lifespan hook that closes the database pool on shutdown.

That is roughly 80 lines of assembly reduced to a four-argument call. A new
restaurant app's entrypoint is
[twenty-four lines total](../../apps/sfcs/src/sfcs_agent/main.py) — that number
*is* the depth.

[`run_rest_graph_with_custom_msg()`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L196)
is the second example. Callers say "run this recipient's conversation with this
message." Hidden inside: acquiring the pool, wrapping it in an
`AsyncPostgresSaver`, compiling the graph, resolving or creating the
restaurant-prefixed thread, creating a customer master record on first contact,
detecting and repairing malformed persisted tool-call tails, invoking, catching
the specific OpenAI 400 that indicates a tool-call mismatch, repairing, retrying
once, and terminating the session if repair fails.

None of that leaks into the call site. That's the whole point.

### Elsewhere

- `requests.get(url)` — one line hides connection pooling, TLS negotiation,
  redirect following, decompression, charset detection, retries.
- A payment SDK's `charge(amount, token)` hides idempotency keys, 3-D Secure
  challenges, network retry with backoff, and currency minor-unit conversion.
- A well-designed file system: `open`, `read`, `write`, `close` — four calls
  over block allocation, journalling, caching, and permissions.

The pattern: **the interface is expressed in the language of the caller's
problem; the implementation is expressed in the language of the mechanism.**
When those two vocabularies are the same, the module is shallow.

### The review question

> After this change, does a caller need to know *more* than before?

If an LLM adds a helper and now the call site is
`build_x(); configure_x(); attach_x(runtime)` instead of `make_x(runtime)`, it
made the module shallower even though it "extracted a function." Extraction that
raises the caller's burden is a regression.

A concrete smell: **a function whose parameters are just forwarded to one other
function, unchanged.** That layer has width but almost no area.

---

## 2. When a shallow layer earns its keep

Section 1 could be misread as "thin wrappers are always bad." They aren't. The
skill is knowing what a thin layer must *buy* to be worth it.

### In this codebase

[`RestaurantGraphAdapter`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L405)
is, by the metric in section 1, shallow. Look at what its methods do:

```python
async def debug_state(self, recipient: str, full_state: bool = False) -> dict:
    return await debug_state(
        recipient,
        full_state=full_state,
        runtime=self.runtime,
        graph_builder=self.graph_builder,
    )
```

That is a pass-through. All four methods are pass-throughs. By Ousterhout's
rule, pass-through methods are a red flag.

**And yet this one is correct**, because it buys two things a plain function
call cannot:

1. **Binding.** Every graph call in the process is permanently attached to
   *this* restaurant's runtime and *this* restaurant's async WhatsApp client.
   Without the adapter, `runtime=` would have to be threaded through every
   webhook handler and router, and the day someone forgets, SFCS answers a
   customer on BNAT's WhatsApp number. The adapter makes that mistake
   unrepresentable rather than merely discouraged.
2. **A substitution seam.** The four methods are exactly the
   [`GraphAdapter` Protocol](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L63).
   An app that needs a different graph topology writes its own class with those
   four methods, and every shared webhook keeps working unchanged. Delete the
   adapter and there is nowhere for that variation to attach.

So the honest rule is: **a thin layer is justified when it changes who owns a
decision, or creates a place to vary behaviour.** It is not justified when it
only renames things.

### Be honest about the cost

This layer is not free, and the doc would be less useful if it pretended
otherwise. Look at
[`debug_state`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L358),
[`debug_state_values`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L384),
and [`debug_state_by_thread`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L322).
Each one opens with the same three lines:

```python
pool = await runtime.settings.database.get_pool()
checkpointer = AsyncPostgresSaver(pool)
graph = graph_builder.compile(checkpointer=checkpointer)
```

Then each is wrapped by a near-identical adapter method. That's the same
sequence written three times in the module functions and three times again in
the adapter. The seam is worth its price; the triplication inside it is just
duplication, and if a fourth debug variant appears, that's the moment to hoist
those three lines into one private helper.

Noticing that distinction — *this* thin layer pays for itself, *that*
repetition does not — is the actual skill.

### Elsewhere

- A repository class over an ORM is worth it when it lets you swap Postgres for
  an in-memory fake in tests. It is not worth it when every method is
  `return self.session.query(X).filter(...)` and no fake exists.
- An HTTP client wrapper is worth it when it centralises auth, base URL, and
  retry policy. It is not worth it when it's `def get(u): return requests.get(u)`.

### The review question

> What decision does this layer own that its caller would otherwise have to make?

If the answer is "none," delete it.

---

## 3. Data classes as domain models

### The idea

A domain model is a value whose *type* tells you what the program is about.
`RestaurantIdentity` is not "a dict with two strings"; it's the answer to
"which restaurant is this?" The value of naming it is that a function signature
saying `identity: RestaurantIdentity` can no longer be handed a customer's
phone number by accident.

Python gives you at least three mechanisms for this, and **this repository uses
all three, for three different reasons.** Understanding *why* each was chosen is
more useful than knowing the syntax of any of them.

### The three mechanisms, as used here

#### `@dataclass(frozen=True, slots=True)` — the default

Used for [`RestaurantIdentity`, `RestaurantPresentation`,
`RestaurantSettingsBundle`, `RestaurantRuntime`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L8),
[`RestaurantPrompts`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/prompts.py#L7),
and [`AgentBindings`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L22).

```python
@dataclass(frozen=True, slots=True)
class RestaurantIdentity:
    rest_ref: str
    waba_namespace: str
```

What each flag buys:

- **`frozen=True`** — assignment after construction raises. This is the
  load-bearing one. These records are read from a dozen places across the
  request lifetime; if any handler could rebind `identity.rest_ref`, you'd have
  a class of bug that only appears under concurrency and is essentially
  undebuggable. Frozen also gives you `__hash__`, so the value can be a dict key
  or live in a set.
- **`slots=True`** — no per-instance `__dict__`. Less memory, faster attribute
  access, and — the real benefit — a typo like `runtime.identtiy = x` raises
  `AttributeError` instead of silently creating a new attribute.

**The caveat the design doc already states, worth repeating:** `frozen=True`
freezes the *bindings*, not the objects behind them. `RestaurantRuntime` is
frozen, but `runtime.async_wa_client` is a live network client with sockets and
mutable internal state. Immutability here means "nobody can swap which client
this runtime points at," not "nothing can change."

#### `TypedDict` — when a framework requires a mapping

[`AgentState`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py#L52)
is a `TypedDict`, not a dataclass. This is not a style choice — LangGraph
serialises graph state into a checkpointer and merges partial updates from
nodes, so the state has to *be* a dict at runtime. `TypedDict` gives you static
field names and types over a plain dict, with zero runtime wrapper.

It also carries something a dataclass can't express here:

```python
messages: Annotated[Sequence[BaseMessage], add_messages]
```

`Annotated[T, metadata]` attaches a **reducer** to the field. When two nodes
both return `messages`, LangGraph doesn't overwrite — it calls `add_messages` to
merge. The merge strategy is part of the type. That's the whole reason
`TypedDict` is the right tool here.

**The trap, live in this file.** Line 91 reads:

```python
ask_for_consent: bool = False
```

That default does nothing. A `TypedDict` is not a dataclass; the assignment sets
a class attribute that is never consulted, and type checkers flag it as an
error. If a graph node reads `state["ask_for_consent"]` before anything has
written the key, it raises `KeyError`. The code is safe today only because every
read site defends itself — [`triage.py:149`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py#L149)
and [`triage.py:214`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py#L214)
both use `state.get("ask_for_consent", False)`. The invariant is duplicated at
every reader instead of held in one place.

This is exactly the kind of thing an LLM writes: it looks like a dataclass, so
it gets a dataclass default. Learn the shape of that mistake — *a construct
borrowed from the wrong mechanism, which the type system does not stop and the
tests do not reach.*

#### `pydantic.BaseModel` — when you need runtime coercion or hooks

[`ContextSchema`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py#L95)
is a Pydantic model. Two features force that choice:

```python
model_config = ConfigDict(arbitrary_types_allowed=True)
```

It holds an `AsyncConnectionPool`, a `WhatsApp` client, and a Supabase `Client`
— none of which Pydantic knows how to validate, hence the escape hatch. And:

```python
def model_post_init(self, __context: Any) -> None:
    if self.thread_handler is None:
        ...
```

A lifecycle hook that lazily constructs a dependent object after the rest of the
model is built.

### Choosing between them

| Question | Answer |
| --- | --- |
| Does a framework need this to be a plain dict at runtime? | `TypedDict` |
| Does data arrive from outside the process (HTTP body, env, JSON) and need validating/coercing? | `pydantic.BaseModel` |
| Is this an internal value assembled from already-trusted parts? | `@dataclass(frozen=True, slots=True)` |
| Is it a fixed set of named alternatives? | `enum.Enum` or `Literal` |

Default to the frozen dataclass. Reach for Pydantic when data crosses a trust
boundary. Reach for `TypedDict` when a library made the decision for you.

### Elsewhere

- **Money.** `Money(amount_minor: int, currency: str)` as a frozen dataclass,
  never a float. The type prevents adding GBP to EUR; the `int` prevents
  `0.1 + 0.2`.
- **Geo.** `LatLon(lat: float, lon: float)` — this single type has prevented
  more argument-order bugs than any amount of care, because `distance(a, b)`
  with two `LatLon`s cannot be called with the coordinates swapped.
- **Identifiers.** `OrderId`, `CustomerId`, `ThreadId` as distinct types even
  though all three are strings underneath. The compiler-visible difference is
  the whole value.

### The review question

> Can I construct a value of this type that means nothing?

If `RestaurantIdentity("", "")` were legal, the type would be documentation
rather than a guarantee. It isn't legal — which brings us to the next section.

---

## 4. Making illegal states unrepresentable

### The idea

There are two places to check that data is sane: at every point of use, or once
at the point of construction. The second is strictly better, because it turns
"we remembered to check" into "there is no unchecked value in existence."

The formal name is a **class invariant**: a property that is true for every
instance from construction until destruction. With immutable values you get this
almost for free — validate in the constructor, and since nothing can change
afterwards, it stays true forever.

### In this codebase

[`RestaurantIdentity.__post_init__`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L15):

```python
def __post_init__(self) -> None:
    rest_ref = self.rest_ref.strip().upper()
    namespace = self.waba_namespace.strip().lower()
    if not rest_ref:
        raise ValueError("rest_ref must not be empty")
    if not namespace:
        raise ValueError("waba_namespace must not be empty")
    object.__setattr__(self, "rest_ref", rest_ref)
    object.__setattr__(self, "waba_namespace", namespace)
```

Two techniques worth separating:

**Rejection.** Empty values raise at construction. Because `IDENTITY` is a
module-level constant in each app's `identity.py`, that exception fires at
*import*, which means at process start — not on the first customer message at
7pm on a Friday. The same is true of
[`RestaurantPrompts.__post_init__`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/prompts.py#L14):
a missing prompt file crashes the app instead of producing an agent with no
system prompt.

**Normalisation.** `rest_ref` is forced uppercase, `waba_namespace` lowercase.
This is the more interesting half. It means every downstream comparison is
already canonical, so [`matches()`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L25)
can be a one-liner and no caller ever has to remember a casing convention. An
entire category of "works locally, fails in production because the env var was
lowercase" simply cannot occur.

**`object.__setattr__` — the frozen escape hatch.** `frozen=True` works by
overriding `__setattr__` to raise. So inside `__post_init__` you cannot write
`self.rest_ref = rest_ref` — it would raise `FrozenInstanceError`. Calling
`object.__setattr__` bypasses the dataclass's override and writes the slot
directly. This is the sanctioned idiom for normalising a frozen dataclass, and
it's safe precisely because it's confined to construction. Seeing it anywhere
*other* than `__post_init__` is a serious smell — that's someone defeating
immutability.

**The counter-example in the same file.**
[`RestaurantSettingsBundle`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L38)
is seven fields, all typed `Any`:

```python
project: Any
database: Any
database_client: Any
llm: Any
payment: Any
maps: Any
waba: Any
```

It's frozen, so nothing gets rebound — but the type system tells you nothing
about what's inside, and nothing stops you passing the maps client as the
payment client. It's a named tuple of anonymous things.

There's a real reason for it: typing those fields properly means the shared
`runtime.py` importing seven concrete settings classes, which couples the
contract module to the configuration implementations. `Any` buys decoupling and
pays with type safety. That's a legitimate trade — but know that you made it,
and know that the guard rail for this bundle lives in
[`load_settings_bundle`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/config/bundle.py#L17)
and its tests, not in the type.

### Elsewhere

- `EmailAddress` that validates in its constructor, so every function taking one
  can skip the regex.
- A `NonEmptyList[T]` type, so `.first()` needs no `Optional` return.
- A state machine modelled as `Draft | Submitted | Paid` rather than
  `status: str` plus a `paid_at: datetime | None` that's only meaningful in one
  of the three states. The union makes "paid with no timestamp" impossible to
  write down.

### When *not* to

- **Don't validate the same thing twice.** If construction guarantees
  non-empty, downstream `if not x:` checks are noise that implies the guarantee
  is untrustworthy.
- **Don't put I/O in a constructor.** Validation should be pure. A
  `__post_init__` that opens a database connection makes the type impossible to
  construct in a test.
- **Don't over-model.** If a field genuinely accepts any string, a wrapper type
  is ceremony.

### The review question

> Where does this value get checked, and could it exist unchecked anywhere?

---

## 5. Partials: turning a constructor into a contract

### The idea

`functools.partial(f, a=1)` returns a new callable with some arguments
pre-filled. Mechanically trivial. Architecturally, it is how you **let a caller
supply data to code that must not know the caller exists.**

That last clause is the point, and it's why the whole `agent_recipe.py`
mechanism works.

### In this codebase

The shared runtime declares the seam as a *function type*:

```python
GraphAdapterFactory = Callable[[RestaurantRuntime], GraphAdapter]
```

([`runtime.py:83`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L83))

Read it as a sentence: *"give me something that takes a runtime and returns an
adapter."* That's the entire contract between an app and the runtime's graph
layer.

But [`RestaurantGraphAdapter.__init__`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L408)
takes a runtime **and** prompts **and** optional tools **and** optional
overrides. It doesn't fit. So the app closes the gap:

```python
PROMPTS = RestaurantPrompts(
    triage=(PROMPT_DIR / "triage_agent_prompt.md").read_text(),
    delivery=(PROMPT_DIR / "delivery_multiagent_prompt.md").read_text(),
    takeaway=(PROMPT_DIR / "takeaway_agent_prompt.md").read_text(),
)
GRAPH_ADAPTER_FACTORY = partial(RestaurantGraphAdapter, prompts=PROMPTS)
```

([`apps/sfcs/.../agent_recipe.py:18`](../../apps/sfcs/src/sfcs_agent/rest_agent/agent_recipe.py#L18))

`partial` binds the app-owned argument and leaves a callable of exactly the
declared shape, waiting for the one thing only the runtime can produce. The two
sides meet in the middle without either importing the other's specifics.

The timing matters too. Prompts are read from disk at *import*, once, and the
resulting object is immutable. Not per request, not per message. (The cost is
stated in the design doc: changing a prompt requires a process restart.)

Note also that `create_restaurant_app` never type-checks the factory or reaches
into it. It calls it: `graph_adapter = graph_adapter_factory(runtime)`
([`app_factory.py:229`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L229)).
Anything callable with the right shape works — a `partial`, a plain function, a
lambda, a class with `__call__`.

### Why `partial` and not the alternatives

| Alternative | Why it loses here |
| --- | --- |
| **Closure** (`def make(): return lambda rt: Adapter(rt, prompts=P)`) | Equivalent, and fine. `partial` is more declarative and its `.func`/`.keywords` are introspectable in tests. Largely taste. |
| **Config object** passed to `create_restaurant_app` | The runtime would need a field for every possible customisation. Every new option changes the shared signature — the opposite of a stable contract. |
| **Subclassing** `RestaurantGraphAdapter` | Couples the app to the shared class's internals; `__init__` signature changes break every app. Inheritance for configuration is a classic over-reach. |
| **Global registry** (`register_prompts("SFCS", P)`) | Import-order dependent, mutable global state, and two apps in one process can collide. [The design doc forbids it explicitly.](../multi_agent_system.md) |

The registry entry deserves emphasis, because a registry is the single most
likely thing an LLM will propose when you ask it to "make this pluggable." It
feels flexible. It is a global mutable dictionary keyed by string, with no
compile-time check that a key exists and no way to run two configurations in one
process. `partial` gives you the same flexibility with none of that.

### Elsewhere

- `partial(logger.log, level=DEBUG)` — a pre-configured logging function.
- `partial(requests.get, timeout=5)` in a client module, so no call site can
  forget the timeout.
- In test fixtures: `make_user = partial(User, tenant=test_tenant)`, so tests
  only specify what they care about.
- Currying in ML/Haskell is the same idea taken to its conclusion: every
  function is one argument at a time, and partial application is how
  configuration flows.

### When *not* to

- **Don't partial to hide a bad signature.** If a function needs eight arguments
  and every call site partials six of them, the function is the problem.
- **Don't bind mutable defaults.** `partial(f, items=[])` shares one list across
  every call, exactly like a mutable default argument.
- **Don't use it where a plain default would do.** `def f(x, timeout=5)` beats
  `partial(f, timeout=5)` when you control `f`.

### The review question

> Does the app-owned value reach the shared code without the shared code
> knowing which app it came from?

---

## 6. Protocols: contracts without inheritance

### The idea

Python's `typing.Protocol` (PEP 544) is **structural typing**: a class satisfies
a protocol by having the right methods, not by inheriting from it. Duck typing,
but checkable.

This matters architecturally because it inverts the dependency. With an abstract
base class, the implementer must import and subclass the contract — the
implementation depends on the abstraction *and* on the module defining it. With
a Protocol, the implementer imports nothing. The contract can be declared in the
consumer's own module.

### In this codebase

[`GraphAdapter`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L62):

```python
@runtime_checkable
class GraphAdapter(Protocol):
    async def run_rest_graph_with_custom_msg(self, recipient: str, **kwargs: Any) -> Any: ...
    async def debug_state(self, recipient: str, full_state: bool = False) -> dict: ...
    async def debug_state_values(self, recipient: str | None = None, config: dict | None = None) -> dict: ...
    async def debug_state_by_thread(self, thread_id: str, full_state: bool = False) -> dict: ...
```

Note what `RestaurantGraphAdapter` inherits from:
[nothing](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L405).
It's a plain class. It satisfies the protocol by shape alone.

This is what makes the "an app may own its own `GraphAdapter`" rule cheap. An
app that needs a fifth graph node writes a class with those four methods.
Nothing to subclass, no base-class constructor to call, no risk of inheriting
behaviour it didn't want. Every shared webhook handler and router keeps working
because they only ever call those four methods.

`@runtime_checkable` additionally permits `isinstance(x, GraphAdapter)` — note
it only checks *method presence*, not signatures, so it's a sanity check, not a
proof.

The same idea appears as bare type aliases in
[`app_factory.py:30`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L30):

```python
SettingsLoader = Callable[[RestaurantIdentity], RestaurantSettingsBundle]
AsyncWaFactory = Callable[[Any, FastAPI], Any]
```

A single-method protocol is just a function type. Prefer the function type when
there's one operation; reach for `Protocol` when the contract is a set of
related operations that must move together — which is precisely the case for
`GraphAdapter`.

### Elsewhere

- `Iterable`, `Sized`, `ContextManager` — the standard library is built on
  structural contracts. Anything with `__iter__` is iterable; nothing inherits
  from `Iterable` to make that true.
- Go's interfaces work exactly this way, and it's why Go packages compose
  without a dependency web.
- Rust traits and Haskell type classes are the nominal-but-external variant: the
  implementation and the contract are still declared separately.

### When *not* to

- **Don't write a protocol with one implementation and no plan for a second.**
  That's speculative generality. `GraphAdapter` earns it because the design
  explicitly anticipates app-owned adapters.
- **Don't use `Protocol` when you want to share implementation.** Protocols
  carry no code. If every implementer needs the same 40 lines, that's a base
  class or, better, a helper function they all call.
- **Don't make the protocol wide.** A protocol's cost is paid by every
  implementer. Four methods is near the practical limit before an app-owned
  adapter becomes a chore to write.

### The review question

> Does the thing implementing this contract have to import the thing defining
> it? If yes, ask why.

---

## 7. The composition root

### The idea

A **composition root** is the single place where the object graph is assembled.
Everywhere else, dependencies arrive as arguments. Mark Seemann's formulation:
compose as close to the application's entry point as possible, and only there.

The alternative — modules reaching for their own dependencies via imports and
globals — is what makes systems untestable and single-tenant by accident.

### In this codebase

The construction path, as one chain:

```
identity.py + agent_recipe.py   (app-owned values)
    -> main.py                  (entrypoint)
    -> create_restaurant_app()  ← the composition root
    -> RestaurantRuntime        (the assembled environment)
    -> GraphAdapterFactory(runtime)
    -> RestaurantGraphAdapter
    -> build_multi_agent_graph()
```

Everything mutable and external — database pool, both WhatsApp clients, LLM
settings, payment settings, Ordelo client — is created in or below
`create_restaurant_app` and stored on exactly one
[`RestaurantRuntime`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py#L51).

The payoff is stated precisely in the design doc: *"Tools therefore use the
exact application runtime rather than module-global settings or clients."*

Watch how it reaches the leaves. The runtime is packed into a
[`ContextSchema`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L276):

```python
context_schema = ContextSchema(
    pool=pool,
    wa_client=runtime.async_wa_client,
    recipient=recipient,
    rest_ref=runtime.identity.rest_ref,
    restaurant_name=runtime.presentation.display_name,
    ...
)
```

and passed into `graph.ainvoke(..., context=context_schema)`. A tool sixty lines
deep in `triage.py` gets the right WhatsApp client through
`runtime.context.wa_client` — an argument, not an import.

If any tool did `from config import wa_client` instead, running SFCS and BNAT in
one process would be impossible and the bug would show up as one restaurant's
customers receiving another's messages.

`RestaurantRuntime` is what functional programmers call a **Reader environment**:
a bundle of ambient capabilities threaded explicitly rather than accessed
globally. Same benefit — you can see every dependency in the signature — without
a monad.

### Elsewhere

- Spring's `@Configuration` classes, ASP.NET's `Startup` — same concept,
  framework-managed.
- A CLI's `main()` parsing args, opening files, and passing handles to pure
  functions.
- An AWS Lambda handler assembling clients at module scope (for warm reuse) and
  passing them into a pure `process(event, deps)`.

### When *not* to

- **Don't let the composition root grow business logic.** It should only wire.
  `create_restaurant_app` decides *what to construct*, never *what to do with a
  customer message*.
- **Don't have two.** The moment a second module also constructs clients, the
  guarantee evaporates.

### The review question

> If I ran two restaurants in one process, would this code confuse them?

That single question catches almost every global-state mistake in this
codebase's problem domain.

---

## 8. The dependency rule

### The idea

Dependencies must point one way, and that way is inward: toward the more stable,
more general, more abstract code. Cycles are forbidden.

This is the structural principle behind hexagonal architecture, clean
architecture, and onion architecture — different names, same rule. The reason
it's non-negotiable is that a cycle means the two modules are, for all practical
purposes, one module: you cannot understand, test, deploy, or delete either
without the other.

### In this codebase

The rule as stated in the design doc:

> The runtime never imports an application package, and one application must
> never import another.

Verify it yourself in the source. Every import in
[`app_factory.py`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py)
is `restaurant_agent_runtime.*`, `fastapi`, `pywa`. Nothing named `sfcs_agent`
or `bnat_agent`. Meanwhile
[`apps/sfcs/main.py`](../../apps/sfcs/src/sfcs_agent/main.py) imports freely
from the runtime.

That asymmetry is the architecture. Apps depend on the runtime; the runtime
depends on nothing above it; app-specific data flows *upward at runtime* through
the `GraphAdapterFactory` callable, never through an import.

There's a second, module-level instance of the same discipline.
[`agent_harness.py`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py)
says in its own docstring:

> This module should have NO imports from other agent modules to avoid circular
> imports.

`triage.py`, `delivery.py`, and `takeaway.py` all import *from* the harness
(`AgentState`, `ContextSchema`, `transfer_to_delivery`, ...). The harness imports
from none of them. Shared vocabulary sits at the bottom; specialisations sit
above.

Notice what makes the handoff tools work without a cycle.
[`transfer_to_delivery`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py#L279)
lives in the harness and ends with:

```python
return Command(
    # Jump to the parent orchestration graph where delivery_agent is defined.
    graph=Command.PARENT,
    goto="delivery_agent",
    update={
        "active_agent": "delivery_agent",
        "messages": update_messages,
    },
)
```

Every reference to the destination is a **string**. `goto` names the parent
graph's node; `active_agent` records it in state so
[`route_after_agent`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py#L25)
can route on a later turn. If the harness imported `delivery.py` to reference
the agent object directly, harness and delivery would import each other and
Python would fail at import time.

The string is deliberate indirection — the same trick a plugin system uses, and
the reason `route_after_agent` has to validate against a hard-coded set of valid
names. That validation is the price of the decoupling: the type system can't
catch a typo in `"delivery_agnet"`, so a runtime guard does.

### The local-import escape hatch, and its honest reading

[`app_factory.py:56`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L56)
and the router mounts at
[lines 256–273](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L256)
put imports *inside* functions rather than at module top level. Legitimate uses
of this pattern: deferring an expensive import, and making a subsystem optional.
It is also, frequently, a way to paper over a cycle that should have been fixed
structurally.

When you see a function-local import in an LLM's output, ask which it is. If the
answer is "the module-level version raised `ImportError: cannot import name`,"
the fix is to move the shared type down a layer, not to hide the import.

### Elsewhere

- Domain layer never imports the web framework — that's why you can unit-test
  order pricing without spinning up HTTP.
- A design system package imports no application code, which is why it can ship
  independently.
- In a monorepo, the dependency graph between packages should be a DAG. If it
  isn't, your build cannot be incremental.

### The review question

> Draw the arrow. Does it point from specific to general?

If an LLM "fixes" an import error by adding a function-local import, treat that
as a design signal, not a fix.

---

## 9. Seams: designing for substitution

### The idea

Michael Feathers' term: a **seam** is a place where you can change behaviour
without editing the code at that place. Seams are what make code testable, and
testability is mostly a proxy for good decoupling — the same property that lets
you swap a vendor later.

### In this codebase

[`create_restaurant_app`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py#L192)
is dense with them:

```python
def create_restaurant_app(
    identity, presentation, graph_adapter_factory, agent_bindings,
    *,
    settings_loader: SettingsLoader = _default_settings_loader,
    async_wa_factory: AsyncWaFactory = _default_async_wa_factory,
    sync_wa_factory: SyncWaFactory = _default_sync_wa_factory,
    register_whatsapp_handlers: bool = True,
    include_order_router: bool = True,
    include_rider_router: bool = True,
    include_thread_router: bool = True,
) -> FastAPI:
```

Three techniques stacked:

**Injected defaults.** `settings_loader` defaults to the real AWS-backed loader.
Production passes nothing. A test passes a stub and builds a full app with no
network, no secrets, no WhatsApp account. The default keeps the common path
simple; the parameter keeps the uncommon path possible. This is the pattern to
imitate — not "make everything injectable," but "give the real thing as the
default."

**Feature flags for optional subsystems.** `include_order_router=False` builds
an app without that router. A test exercising the graph doesn't drag in order
webhooks.

**Keyword-only arguments (`*`).** Everything after the bare `*` must be passed
by name. This is API-stability engineering: you can reorder, insert, or
deprecate these parameters without breaking a single caller, because no caller
depends on position. Use `*` for anything optional or configuration-shaped. The
same technique appears on
[`build_triage_agent(*, model, system_prompt, extra_tools=())`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py#L251)
and on the runner's `*, runtime, graph_builder`
([`agent_runner.py:206`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L206)).

**The customisation ladder.** The extension points are deliberately ordered by
blast radius, and it's worth internalising the ordering as a decision procedure:

| Need | Mechanism | Blast radius |
| --- | --- | --- |
| Different wording | Edit the app's prompt file | One app, no code |
| One more tool on a standard node | `extra_tools_by_agent` | One node, one app |
| Replace a whole node | `agent_overrides` | One node, one app |
| Different graph shape or state | App-owned `GraphAdapter` | One app |
| Behaviour two apps both need | Promote into the shared runtime | Everything — needs review |

Always take the lowest rung that works. An LLM asked to "add a loyalty check to
triage" may well restructure the graph; the correct answer is
`extra_tools_by_agent={"triage_agent": [check_loyalty]}` and nothing else.

And note that the ladder is *enforced*, not merely documented —
[`RestaurantGraphAdapter.__init__`](../../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py#L420)
raises on unknown agent names, on a node appearing in both maps, and on an
override lacking `ainvoke`. Misuse fails at startup, not in front of a customer.

### Elsewhere

- A `clock: Callable[[], datetime] = datetime.now` parameter, so time-dependent
  logic is testable without freezing global time.
- An `http_client` parameter defaulting to a real session, so integration tests
  inject a recorded transport.
- Constructor injection generally: if a class creates its own dependencies, you
  have no seam and must resort to monkey-patching.

### When *not* to

- **Don't add a seam with no second implementation and no test using it.** Every
  parameter widens the interface (section 1) and must be paid for.
- **Don't inject what never varies.** `math.pi` does not need a seam.

### The review question

> To test this, do I have to patch a module global?

If yes, the seam is missing. If the answer is "I'd inject a fake," the design is
already right.

---

## 10. Review checklist for LLM-written code

Run this over any non-trivial diff. Roughly ordered by how much damage the
failure causes.

**Dependency direction**
- [ ] Does anything in `packages/restaurant-agent-runtime/` now import from `apps/`? *(Hard stop — this breaks the architecture.)*
- [ ] Does one app import another?
- [ ] Are there new function-local imports? For each: is it deferring cost, or hiding a cycle?
- [ ] Does `agent_harness.py` now import from `triage.py`, `delivery.py`, or `takeaway.py`?

**Runtime isolation**
- [ ] Would this code behave correctly with two restaurants in one process?
- [ ] Does any new module read settings or clients from a module-level global instead of receiving them?
- [ ] Does every new tool get its WhatsApp client from `runtime.context`, not an import?

**Module depth**
- [ ] Does a caller now need to know more than before this change?
- [ ] Is the new function a pure pass-through? If so, what does it buy — binding, or a seam? If neither, delete it.
- [ ] Was one clear function split into two functions with intertwined interfaces?

**Data modelling**
- [ ] Is the new record a frozen dataclass? If it's Pydantic, does it actually need validation or hooks? If it's a `TypedDict`, does a framework require a dict?
- [ ] Does a `TypedDict` field have an `= default`? *(It does nothing. See section 3.)*
- [ ] Can this type be constructed in a meaningless state?
- [ ] Is a new field typed `Any` where a real type was available?
- [ ] Does `object.__setattr__` appear outside `__post_init__`?

**Extension mechanism**
- [ ] Did it take the lowest rung of the customisation ladder that would work?
- [ ] Did it introduce a global registry, a plugin dict, or a string-keyed lookup where a `partial` or a parameter would do?
- [ ] Did it subclass a shared class to configure it, instead of passing arguments?
- [ ] Did it add a `Protocol` or abstraction with exactly one implementation and no second in sight?

**Seams and signatures**
- [ ] Are new optional/configuration parameters keyword-only (after `*`)?
- [ ] Can the new code be tested without patching a module global?
- [ ] Do new failure modes raise at startup, or only when a customer hits them?

**Prompt-shaped questions to ask the LLM back**

When something looks off, these get better results than "fix it":

- *"What does this new layer own that its caller would otherwise decide?"*
- *"Show me the dependency arrows for the modules you touched."*
- *"Solve this using only `extra_tools_by_agent` — no changes to the shared runtime."*
- *"This introduces a registry. Give me the version that uses `functools.partial` instead."*
- *"Which of these values can be constructed in an invalid state, and where would that surface?"*

---

## 11. Further reading

### Start here

**John Ousterhout — *A Philosophy of Software Design***
The origin of the deep/shallow module vocabulary and of "complexity is what
makes software hard, and it accumulates incrementally." Short — a weekend — and
the highest return per page of anything on this list. The chapters on
information hiding, pass-through methods, and "different layer, different
abstraction" are directly the material in sections 1 and 2. If you read one
thing, read this.

**Michael Feathers — *Working Effectively with Legacy Code***
Where "seam" comes from. Nominally about legacy systems; actually the best
practical book on why dependencies must be injectable. Section 9 is its ideas
applied to `create_restaurant_app`.

### Design of types and domains

**Scott Wlaschin — *Domain Modeling Made Functional***, and his talk
*"Domain Modelling Made Functional"* / the article series "Designing with Types"
on fsharpforfunandprofit.com.
F#, but the ideas transfer to Python dataclasses without loss. This is the
canonical treatment of "make illegal states unrepresentable" (section 4).

**Eric Evans — *Domain-Driven Design***
The source of "value object," "entity," and "aggregate." Dense. Vaughn Vernon's
*Implementing Domain-Driven Design* is the more practical companion if Evans is
heavy going.

### Structure and dependencies

**Alistair Cockburn — "Hexagonal Architecture" (Ports and Adapters)**
The clearest short statement of the dependency rule (section 8). `GraphAdapter`
is literally a port; `RestaurantGraphAdapter` is an adapter.

**Robert C. Martin — *Clean Architecture***
Same rule at book length, plus the SOLID principles. Read the Dependency
Inversion chapter and treat the rest as optional.

**Mark Seemann — *Dependency Injection Principles, Practices, and Patterns***
The definitive treatment of the composition root (section 7). .NET examples;
the principles are language-independent. Seemann's blog (blog.ploeh.dk) is
excellent and free.

### Python specifics — canonical docs

- [`dataclasses`](https://docs.python.org/3/library/dataclasses.html) — read the sections on `frozen`, `slots`, and `__post_init__`.
- [`functools.partial`](https://docs.python.org/3/library/functools.html#functools.partial)
- [PEP 544 — Protocols: Structural subtyping](https://peps.python.org/pep-0544/) — surprisingly readable; the motivation section is the argument for section 6.
- [PEP 589 — TypedDict](https://peps.python.org/pep-0589/)
- [PEP 484 — Type Hints](https://peps.python.org/pep-0484/) — for `Callable[...]` type aliases as contracts.
- [`typing.Annotated`](https://docs.python.org/3/library/typing.html#typing.Annotated) — the mechanism behind `Annotated[Sequence[BaseMessage], add_messages]`.
- [Pydantic documentation](https://docs.pydantic.dev/) — specifically model config, `arbitrary_types_allowed`, and `model_post_init`.

### On working with LLMs on architecture

There is no settled canon here, so treat this as a working practice rather than
a citation:

- Give the LLM the constraint, not just the goal. "Add a loyalty tool" invites a
  redesign; "add a loyalty tool using `extra_tools_by_agent`, changing no file
  under `packages/`" gets one correct diff.
- Ask for the dependency arrows before you ask for the code.
- When output looks over-engineered, ask for the version with one fewer layer
  and compare. The comparison is usually more informative than either answer.
- Keep this repository's architectural rules in `CLAUDE.md` /
  `CONSTITUTION.md` so they're in context by default rather than remembered
  per-prompt.

### Within this repository

- [`docs/multi_agent_system.md`](../multi_agent_system.md) — the ownership model and customisation contract.
- [`docs/guides/agent-runtime-composition.html`](./agent-runtime-composition.html) — visual navigator for where each construct is created and consumed.
- [`docs/architecture/shared-agent-runtime-decisions.md`](../architecture/shared-agent-runtime-decisions.md) — the decision record, including options that were rejected. Reading rejected options is one of the fastest ways to absorb a codebase's judgement.
- [`docs/glossary.md`](../glossary.md) and [`docs/domain/platform-domain-model.md`](../domain/platform-domain-model.md) — platform vocabulary and authority rules.
