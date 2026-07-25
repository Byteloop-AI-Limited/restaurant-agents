"""
Agent router for directing user queries to specialized agents
    . Analyzes user intent to determine the appropriate specialized agent
    . Routes conversations to queryAgent, takeawayAgent, or dineinAgent
    . Uses LangChain for intent classification and routing decisions
    . Implements a structured output format for agent selection
    . Maintains conversation context across agent handoffs
  Functions/Classes:
    . Router - TypedDict for structured agent routing decisions
    . run_router_agent - Processes user messages and determines routing
"""

# %%
from typing import Literal
from typing_extensions import TypedDict
from restaurant_agent_core.services.lg_utils import LLM_CLIENT as llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage

# %%

router_agent_prompt_str = """
# Agent Router Prompt

Given the ongoing conversation between a Human and the AI, determine which of the specialized agents is best suited to handle the user's last turn. Respond with **ONLY** the name of the agent that should act next.

## Agent Capabilities and Roles

### takeawayAgent
- Handles all aspects of takeaway orders
- Manages order placement and modifications
- Verifies and confirms payments for takeaway orders
- Sends order receipts and updates for takeaway orders
- Does NOT handle food item searches

### dineinAgent
- Handles dine-in inquiries and reservations
- Manages booking details, including date, time, and number of guests
- Answers questions related to dining in, such as seating availability
- Handles requests for eating with friends (group reservations)
- I want to eat at the restaurant with my friends

### queryAgent
- Handles food search queries where the user provides just a food item name and nothing else
- Handles general queries about the restaurant
- Handles user complaints, general feedback
- Provides information like location, phone number, opening hours, and website
- Note: Should NOT handle complex food searches or building orders

## Reasoning Process
1. Identify the core intent of the user's last message. What is the user trying to achieve?
2. Match the identified intent to the capabilities of the available agents. Which agent is specifically designed to handle this type of request?
3. Select the most appropriate agent.

## Few Shot Examples

**Example 1:**
```
Human: What's your address?
Response: queryAgent
Human: Okay, can I order a chicken biryani for pickup?
Response: takeawayAgent
```

**Example 2:**
```
Human: Do you have any tables available tonight?
Response: dineinAgent
```

**Example 3:**
```
Human: I have made the payment/ paid/ completed payment
Response: takeawayAgent
```

**Example 4:**
```
Human: chicken biryani
Response: queryAgent
```
"""

# %% Create agent chain
agents = ["queryAgent", "takeawayAgent", "dineinAgent"]


class Router(TypedDict):
    """Agent to route to next. If no agents needed, route to queryAgent."""

    next_agent: Literal[*agents]


router_agent = llm.with_structured_output(Router)

router_agent_prompt = ChatPromptTemplate.from_messages(
    [("system", router_agent_prompt_str), ("placeholder", "{messages}")]
)

router_agent = router_agent_prompt | llm.with_structured_output(Router)


# %%
def run_router_agent(human_message: str):
    messages = [HumanMessage(human_message)]
    return router_agent.invoke({"messages": messages})["next_agent"]


# %%
"""
# %%
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

messages = [
    AIMessage("I understand you want to takeaway"),
    HumanMessage("I want to eat peacefull at home."),
    HumanMessage("I need to call to make a reservation"),
    HumanMessage("I am having trouble with the payment"),
]

router_agent.invoke({"messages": messages})['next_agent']

# %%

run_router_agent("help with query")
# %%
"""
