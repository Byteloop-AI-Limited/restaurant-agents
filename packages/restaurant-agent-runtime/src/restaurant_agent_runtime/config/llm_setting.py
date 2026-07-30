"""
LLM settings and client configuration for the agent
  . Defines LLMSettings for OpenAI model and API key management
  . Provides llm_client property to instantiate ChatOpenAI client
  . Loads configuration from AWS environment settings
  . Configures ChatOpenAI with temperature=0, max_retries=2
  Functions/Classes:
    . LLMSettings
    . llm_settings
"""

# %%
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from restaurant_agent_runtime.utils.aws_setting import agent_env
from langchain_openai import ChatOpenAI


class LLMSettings(BaseSettings):
    model: str = Field(..., alias="llm_model")
    openai_api_key: str = Field(..., alias="llm_openai_api_key")
    model_config = SettingsConfigDict(extra="allow")

    def _build_client(self, *, parallel_tool_calls: bool | None = None) -> ChatOpenAI:
        model_kwargs = {}
        if parallel_tool_calls is not None:
            model_kwargs["parallel_tool_calls"] = parallel_tool_calls

        return ChatOpenAI(
            model=self.model,
            openai_api_key=self.openai_api_key,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            model_kwargs=model_kwargs,
        )

    @property
    def llm_client(self):
        """
        Returns a ChatOpenAI instance using the model and API key from settings,
        with temperature=0, max_tokens=None, timeout=None, max_retries=2.
        """
        return self._build_client()

    @property
    def llm_client_single_tool_turn(self):
        """Return a client that disables parallel tool calls.

        The WhatsApp agents rely on middleware that appends AI messages after tool
        execution, so they must keep tool-calling to one tool per assistant turn.
        """
        return self._build_client(parallel_tool_calls=False)


llm_settings = LLMSettings(**agent_env)
# %% Usage
# sheet =g_client.open("elai_takeaway_menu").sheet1
# sheet.get_all_records()

# %% How to create encoded creds
# with open(f'{project_setting.get_project_root()}/google_creds.json', "r") as file:
#     json_content = file.read()

# encoded_credentials = base64.b64encode(json_content.encode()).decode()
