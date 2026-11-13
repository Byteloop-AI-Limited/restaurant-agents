"""PostgreSQL and Supabase settings for one restaurant runtime.

``PgSetting`` owns lazy client and connection-pool construction. Instances are
created by ``load_settings_bundle``; this module does not load AWS settings or
publish process-global database clients. Server clients use the service key;
private shared order tables are not accessible using browser credentials.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from supabase import (
    create_client,
    Client,
    create_async_client,
    AsyncClient,
    AuthApiError,
    PostgrestAPIError,
    AuthError,
)
from loguru import logger
from psycopg_pool import AsyncConnectionPool
from typing import Optional
from pydantic import Field

# %%


class PgSetting(BaseSettings):
    db_uri: str = Field(..., alias="sbase_ordelo_db_uri")
    vec_db_uri: str = Field(..., alias="sbase_ordelo_vec_db_uri")
    rest_url: str = Field(..., alias="sbase_ordelo_rest_url")
    rest_key: str = Field(..., alias="sbase_ordelo_rest_key")
    service_key: str = Field(..., alias="sbase_ordelo_service_key")
    collection_name: Optional[str] = Field(None, alias="sbase_ordelo_collection_name")
    _async_pool: Optional[AsyncConnectionPool] = None

    @property
    def connection_kwargs(self):
        return {
            "autocommit": True,
            "prepare_threshold": None,
            "connect_timeout": 10,  # Connection timeout in seconds
            "keepalives": 1,  # Enable TCP keepalives
            "keepalives_idle": 60,  # Seconds of inactivity before sending keepalive
            "keepalives_interval": 10,  # Seconds between keepalives
            "keepalives_count": 5,  # Number of keepalives before considering connection dead
        }

    @property
    def pool_kwargs(self):
        return {
            "min_size": 1,  # Only ever open 1 connection at a time in lambda
            "max_size": 5,  # Maximum connections in pool
            "max_idle": 30,  # if lambda is idles > 30s, automatically close idle sockets
            "timeout": 20,  # when aquiring, wait up to 20s before throwing "timeout"
            "reconnect_timeout": 10,  # If socket is broken, attempts to reconnect automatically
            "open": False,  # We'll open it explicitly
        }

    @property
    def headers(self):
        return {
            "apiKey": self.service_key,
            "Accept": "application/json",
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }

    @property
    def service_headers(self):
        return {
            "apiKey": self.service_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @property
    def rest_endpoint_function(self):
        return f"{self.rest_url}/rest/v1/rpc/search_documents"

    @property
    def rest_endpoint(self):
        return f"{self.rest_url}/rest/v1"

    @property
    def client(self) -> Client:
        if not self.rest_url or not self.service_key:
            raise ValueError(
                "Both rest_url and service_key must be provided for Supabase client"
            )
        return create_client(self.rest_url, self.service_key)

    @property
    def async_client(self) -> AsyncClient:
        if not self.rest_url or not self.service_key:
            raise ValueError(
                "Both rest_url and service_key must be provided for Supabase async client"
            )
        return create_async_client(self.rest_url, self.service_key)

    async def get_pool(self) -> AsyncConnectionPool:
        # If pool doesn't exist, or if it exists but was closed
        if self._async_pool is None or self._async_pool.closed:
            # Optional: Add logging here if you want to know when a closed pool is being recreated
            logger.info("AsyncConnectionPool is None or closed, creating a new one.")
            # temp_db_uri = "?options=-c%20search_path%3Delas"
            self._async_pool = AsyncConnectionPool(
                conninfo=self.db_uri,
                # conninfo=self.db_uri + temp_db_uri,
                kwargs=self.connection_kwargs,
                min_size=self.pool_kwargs["min_size"],
                max_size=self.pool_kwargs["max_size"],
                max_idle=float(self.pool_kwargs["max_idle"]),
                timeout=float(self.pool_kwargs["timeout"]),
                reconnect_timeout=float(self.pool_kwargs["reconnect_timeout"]),
                check=AsyncConnectionPool.check_connection,
                open=False,  # Initialize with open=False
            )
            await self._async_pool.open()  # Explicitly open it
        return self._async_pool

    async def close_pool(self) -> None:
        pool = self._async_pool
        if pool is not None and not pool.closed:
            logger.info("Closing AsyncConnectionPool")
            await pool.close()
        self._async_pool = None

    def check_connection(self, table_name: str) -> bool:
        """
        Checks the connection to Supabase by attempting a simple query on a table.

        Args:
            table_name: The name of the table to query.

        Returns:
            True if the connection and query are successful, False otherwise.
        """
        try:
            response = self.client.table(table_name).select("*").limit(1).execute()
            logger.info(
                f"Successfully connected and queried table '{table_name}'. Response count: {response.count}"
            )
            return True
        except PostgrestAPIError as e:
            logger.error(
                f"Supabase API Error checking connection to table '{table_name}': {e}"
            )
            return False
        except AuthApiError as e:
            logger.error(
                f"Supabase Authentication Error checking connection to table '{table_name}': {e}"
            )
            return False
        except AuthError as e:
            logger.error(
                f"Supabase Authorization Error checking connection to table '{table_name}': {e}"
            )
            return False
        except Exception as e:
            # Catch other potential exceptions (network issues, etc.)
            logger.error(
                f"An unexpected error occurred checking connection to table '{table_name}': {e}"
            )
            return False

    model_config = SettingsConfigDict(extra="allow")
