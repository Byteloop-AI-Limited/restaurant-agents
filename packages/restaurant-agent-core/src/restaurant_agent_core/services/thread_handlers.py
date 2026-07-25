"""
Thread management utilities for conversation tracking
  . Maintains in-memory dictionary of conversation threads
  . Tracks active and inactive thread states
  . Creates and retrieves threads by phone number
  . Manages thread lifecycle and timestamps
  Functions/Classes:
    . thread_dict
    . get_active_thread
    . create_new_entry
    . create_new_thread
    . close_thread
"""

# %%
import uuid
from datetime import datetime

# Initialize the main dictionary
thread_dict = {}


def get_active_thread(from_number):
    """
    Retrieves the active thread for a given from_number.
    """
    if from_number not in thread_dict:
        return None

    for thread in reversed(thread_dict[from_number]):
        if thread["is_active"]:
            return thread

    return None


def create_new_entry(from_number):
    """
    Creates a new entry in the dictionary for a given from_number.
    """
    if from_number not in thread_dict:
        thread_dict[from_number] = []

    active_thread = get_active_thread(from_number)
    if active_thread is not None:
        active_thread["is_active"] = False

    new_thread = {
        "thread_id": str(uuid.uuid4()),
        "thread_ts": datetime.now().isoformat(),
        "is_active": True,
    }

    thread_dict[from_number].append(new_thread)
    return new_thread


def add_new_thread(from_number):
    """
    Adds a new thread for a given from_number, marking it as active
    and marking the previous one as inactive.
    """
    if from_number in thread_dict:
        # Mark all existing threads as inactive
        for thread in thread_dict[from_number]:
            thread["is_active"] = False

    # Create and add the new active thread
    return create_new_entry(from_number)


# %%


class ThreadHandlerLocal:
    def __init__(self, pool=None):
        # pool parameter is kept for compatibility but not used
        pass

    async def create_thread(self, from_number):
        thread = create_new_entry(from_number)
        return {
            "thread_id": thread["thread_id"],
            "from_number": from_number,
            "thread_ts": thread["thread_ts"],
            "is_active": thread["is_active"],
        }

    async def get_active_thread(self, from_number):
        thread = get_active_thread(from_number)
        if thread is None:
            return None
        return {
            "thread_id": thread["thread_id"],
            "from_number": from_number,
            "thread_ts": thread["thread_ts"],
            "is_active": thread["is_active"],
        }

    async def make_threads_inactive(self, from_number):
        if from_number in thread_dict:
            count = 0
            for thread in thread_dict[from_number]:
                if thread["is_active"]:
                    thread["is_active"] = False
                    count += 1
            return {"message": f"{count} thread(s) marked as inactive."}
        return {"message": "0 thread(s) marked as inactive."}

    async def get_or_create_thread(self, from_number):
        active_thread = get_active_thread(from_number)
        if active_thread:
            return active_thread["thread_id"], False
        else:
            new_thread = create_new_entry(from_number)
            return new_thread["thread_id"], True


# %%
# Example usage:

# # Create a new entry
# thread1 = create_new_entry(from_number)
# print("Thread 1:", thread1)

# # # Get the active thread
# # active_thread = get_active_thread(from_number)
# # print("Active thread:", active_thread)

# # # Add a new thread
# thread2 = add_new_thread(from_number)
# print("Thread 2:", thread2)

# # # Get the new active thread
# new_active_thread = get_active_thread(from_number)
# print("New active thread:", new_active_thread)

# # # Print the entire dictionary
# # print("Thread dictionary:", thread_dict)
