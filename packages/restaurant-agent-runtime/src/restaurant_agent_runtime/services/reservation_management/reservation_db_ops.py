"""
Reservation database operations and models
  . Defines ReservationModel Pydantic model for table bookings
  . Generates unique reservation IDs with hashing
  . Processes reservation data into database
  . Manages reservation confirmation status
  . Handles reservation timestamps and tracking
  Functions/Classes:
    . ReservationModel
    . process_reservation_into_db
"""

# %%
import hashlib
from datetime import datetime

from pydantic import BaseModel, Field, model_validator
import psycopg

from restaurant_agent_runtime.config import project_settings, logger


# %% define variables


SALT = project_settings.salt
ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# %% Data models


class ReservationModel(BaseModel):
    rest_ref: str = Field(exclude=True)
    reservation_id: str | None = Field(default=None)
    seq_id: int
    recipient: str
    thread_id: str
    reservation_dt: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    reservation_ts: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )
    confirmation_status: str = "not_confirmed"

    @model_validator(mode="after")
    def generate_reservation_id(self) -> "ReservationModel":
        self.rest_ref = self.rest_ref.strip().upper()
        if not self.rest_ref:
            raise ValueError("rest_ref must not be empty")
        if not self.reservation_id:
            self.reservation_id = (
                f"{self.rest_ref}-{self._create_reservation_id()}-{self.seq_id}"
            )
        return self

    def _create_reservation_id(self) -> str:
        number = self.recipient[-4:]
        """Encodes a 4-digit number string into a 4-character string."""
        if not len(number) == 4 or not number.isdigit():
            raise ValueError("Number must be a 4-digit string")

        salted_number = f"{number}{SALT}{self.reservation_dt}"
        hashed_number = hashlib.sha256(salted_number.encode()).hexdigest()

        encoded_chars: str = ""
        for i in range(4):
            index = int(hashed_number[i * 2 : i * 2 + 2], 16) % len(ALPHABET)
            encoded_chars += ALPHABET[index]
        return encoded_chars.upper()


# %%
class ReservationHandler:
    def __init__(self, pool):
        self.pool = pool

    async def get_seq_num(self):
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    await cur.execute(
                        """
                        SELECT * FROM get_next_daily_seq(%s)
                        """,
                        (datetime.now().strftime("%Y-%m-%d"),),
                    )
                    result = await cur.fetchone()
                return result["get_next_daily_seq"]
        except psycopg.Error as e:
            # Handle exceptions as needed
            print(f"Error in get_active_thread: {e}")
            raise

    async def create_reservation_record(self, food_order: ReservationModel):
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    record = food_order.model_dump()
                    values = tuple(record.values())
                    cols = record.keys()
                    await cur.execute(
                        f"""
                        INSERT INTO
                        reservation(
                            {",".join(cols)}
                            )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        values,
                    )
                return True
        except psycopg.Error as e:
            # Handle exceptions as needed
            print(f"Error in create_food_order: {e}")
            raise

    async def update_reservation_record(self, reservation_id: str):
        try:
            async with self.pool.connection() as conn:
                reservation_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE reservation
                        SET reservation_ts = %s, confirmation_status = 'confirmed'
                        WHERE reservation_id = %s
                        """,
                        (reservation_ts, reservation_id),
                    )

                    if cur.rowcount == 0:
                        print(f"No reservation found with ID: {reservation_id}")
                        return False

                return True
        except psycopg.Error as e:
            print(f"Error in update_reservation_record: {e}")
            raise


# %% test


async def process_reservation_into_db(
    pool,
    recipient: str,
    thread_id: str,
    *,
    rest_ref: str,
):
    res_handler = ReservationHandler(pool)
    seq_id = await res_handler.get_seq_num()

    res_payload = {
        "recipient": recipient,
        "thread_id": thread_id,
        "seq_id": seq_id,
        "rest_ref": rest_ref,
    }
    _record = ReservationModel(**res_payload)
    reservation_id = _record.reservation_id

    if await res_handler.create_reservation_record(_record):
        logger.info(f"Reservation {reservation_id} inserted into db")
        return reservation_id
    else:
        return False


async def update_reservation_in_db(pool, reservation_id: str):
    res_handler = ReservationHandler(pool)
    update_response = await res_handler.update_reservation_record(reservation_id)
    return update_response


# %%


"""
# %% Test
async with AsyncConnectionPool(
        conninfo=pg_settings.db_uri,
        max_size=20,
        kwargs=pg_settings.connection_kwargs,
) as pool:
    op = await update_reservation_in_db(pool, reservation_id="RES-UOYH-23")
    print(op)

"""
