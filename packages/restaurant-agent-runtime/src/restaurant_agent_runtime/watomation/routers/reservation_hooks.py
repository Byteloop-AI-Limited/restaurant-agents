"""
Reservation webhook handlers for the dine-in system. These events are called from the reservation service.
    . Processes reservation form submission webhooks
    . Sends confirmation messages to customers via WhatsApp
    . Provides reservation ID confirmation to users
    . Handles reservation confirmation and decline notifications
  Functions/Classes:
    . reservation_form_submitted - Handles reservation form submission and sends confirmation message
    . reservation_confirmed - Handles reservation confirmation and sends WhatsApp message
    . reservation_declined - Handles reservation decline and sends WhatsApp message
"""

# %%

from fastapi import APIRouter, Depends, HTTPException, Request
from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import RestaurantRuntime
from restaurant_agent_runtime.web.dependencies import get_restaurant_runtime

# %% Define Router

router = APIRouter(tags=["reservation-hooks"])


# %% When reservation form is submitted


@router.post("/{rest_ref}/reservation-form-submitted")
async def reservation_form_submitted(
    rest_ref: str,
    request: Request,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
):
    """
    Handles reservation form submission webhook from reservation service.
    Receives reservation_id in the request body.
    Queries the reservation table to get the recipient.
    Sends WhatsApp confirmation message to the user.

    Path parameters:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN")
        Must match the prefix of reservation_id (e.g., if reservation_id is "ELAS-RESV-22", rest_ref must be "ELAS")

    Expected request body:
    {
        "reservation_id": "ELAS-RESV-22"
    }
    """
    try:
        data = await request.json()
        reservation_id = data.get("reservation_id")

        if not reservation_id:
            raise HTTPException(
                status_code=400, detail="reservation_id is required in request body"
            )

        # Extract rest_ref from reservation_id (format: ELAS-RESV-22)
        reservation_id_parts = reservation_id.split("-")
        if len(reservation_id_parts) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reservation_id format: {reservation_id}. Expected format: RESTREF-RESV-XX",
            )

        reservation_rest_ref = reservation_id_parts[0].upper()
        rest_ref_upper = rest_ref.upper()

        if not runtime.identity.matches(rest_ref_upper):
            raise HTTPException(
                status_code=404, detail=f"Restaurant not found: {rest_ref}"
            )

        # Validate that rest_ref in URL matches rest_ref in reservation_id
        if reservation_rest_ref != rest_ref_upper:
            raise HTTPException(
                status_code=400,
                detail=f"rest_ref mismatch: URL has '{rest_ref_upper}' but reservation_id has '{reservation_rest_ref}'",
            )

        logger.info(
            f"Reservation form submitted webhook received for rest_ref: {rest_ref_upper}, reservation_id: {reservation_id}"
        )

        # Query reservation table to get recipient
        response = (
            runtime.settings.database_client.table("reservation")
            .select("recipient")
            .eq("reservation_id", reservation_id)
            .execute()
        )

        if len(response.data) == 0:
            logger.error(f"Reservation not found: {reservation_id}")
            raise HTTPException(
                status_code=404, detail=f"Reservation {reservation_id} not found"
            )

        recipient = response.data[0]["recipient"]

        # Send WhatsApp confirmation message
        message_text = (
            f"Your reservation request has been received! 🎉\n"
            f"Reservation ID: *{reservation_id}*\n\n"
            "We'll be in touch shortly to confirm your booking. Thank you!"
        )

        await runtime.async_wa_client.send_message(
            to=recipient,
            text=message_text,
        )

        logger.info(
            f"Reservation confirmation message sent to {recipient} for reservation {reservation_id}"
        )

        return {
            "status": "success",
            "rest_ref": rest_ref_upper,
            "reservation_id": reservation_id,
            "recipient": recipient,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing reservation form submission: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# %% When reservation is confirmed


@router.get("/{rest_ref}/reservation-confirmed/{reservation_id}")
async def reservation_confirmed(
    rest_ref: str,
    reservation_id: str,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
):
    """
    Handles reservation confirmation webhook from reservation service.
    Queries the reservation table to get the recipient.
    Sends WhatsApp confirmation message to the user.

    Path parameters:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN")
        reservation_id: Reservation ID (e.g., "ELAS-RESV-22")
        Must match the prefix of reservation_id (e.g., if reservation_id is "ELAS-RESV-22", rest_ref must be "ELAS")
    """
    try:
        # Extract rest_ref from reservation_id (format: ELAS-RESV-22)
        reservation_id_parts = reservation_id.split("-")
        if len(reservation_id_parts) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reservation_id format: {reservation_id}. Expected format: RESTREF-RESV-XX",
            )

        reservation_rest_ref = reservation_id_parts[0].upper()
        rest_ref_upper = rest_ref.upper()

        if not runtime.identity.matches(rest_ref_upper):
            raise HTTPException(
                status_code=404, detail=f"Restaurant not found: {rest_ref}"
            )

        # Validate that rest_ref in URL matches rest_ref in reservation_id
        if reservation_rest_ref != rest_ref_upper:
            raise HTTPException(
                status_code=400,
                detail=f"rest_ref mismatch: URL has '{rest_ref_upper}' but reservation_id has '{reservation_rest_ref}'",
            )

        logger.info(
            f"Reservation confirmed webhook received for rest_ref: {rest_ref_upper}, reservation_id: {reservation_id}"
        )

        # Query reservation table to get recipient
        response = (
            runtime.settings.database_client.table("reservation")
            .select("recipient")
            .eq("reservation_id", reservation_id)
            .execute()
        )

        if len(response.data) == 0:
            logger.error(f"Reservation not found: {reservation_id}")
            raise HTTPException(
                status_code=404, detail=f"Reservation {reservation_id} not found"
            )

        recipient = response.data[0]["recipient"]

        # Send WhatsApp confirmation message
        message_text = (
            f"Great news! Your reservation (ID: {reservation_id}) has been confirmed. "
            "We look forward to welcoming you to our restaurant. See you soon!"
        )

        await runtime.async_wa_client.send_message(
            to=recipient,
            text=message_text,
        )

        logger.info(
            f"Reservation confirmed message sent to {recipient} for reservation {reservation_id}"
        )

        return {
            "status": "success",
            "rest_ref": rest_ref_upper,
            "reservation_id": reservation_id,
            "recipient": recipient,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing reservation confirmation: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# %% When reservation is declined


@router.get("/{rest_ref}/reservation-declined/{reservation_id}")
async def reservation_declined(
    rest_ref: str,
    reservation_id: str,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
):
    """
    Handles reservation decline webhook from reservation service.
    Queries the reservation table to get the recipient.
    Sends WhatsApp decline message to the user.

    Path parameters:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN")
        reservation_id: Reservation ID (e.g., "ELAS-RESV-22")
        Must match the prefix of reservation_id (e.g., if reservation_id is "ELAS-RESV-22", rest_ref must be "ELAS")
    """
    try:
        # Extract rest_ref from reservation_id (format: ELAS-RESV-22)
        reservation_id_parts = reservation_id.split("-")
        if len(reservation_id_parts) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reservation_id format: {reservation_id}. Expected format: RESTREF-RESV-XX",
            )

        reservation_rest_ref = reservation_id_parts[0].upper()
        rest_ref_upper = rest_ref.upper()

        if not runtime.identity.matches(rest_ref_upper):
            raise HTTPException(
                status_code=404, detail=f"Restaurant not found: {rest_ref}"
            )

        # Validate that rest_ref in URL matches rest_ref in reservation_id
        if reservation_rest_ref != rest_ref_upper:
            raise HTTPException(
                status_code=400,
                detail=f"rest_ref mismatch: URL has '{rest_ref_upper}' but reservation_id has '{reservation_rest_ref}'",
            )

        logger.info(
            f"Reservation declined webhook received for rest_ref: {rest_ref_upper}, reservation_id: {reservation_id}"
        )

        # Query reservation table to get recipient
        response = (
            runtime.settings.database_client.table("reservation")
            .select("recipient")
            .eq("reservation_id", reservation_id)
            .execute()
        )

        if len(response.data) == 0:
            logger.error(f"Reservation not found: {reservation_id}")
            raise HTTPException(
                status_code=404, detail=f"Reservation {reservation_id} not found"
            )

        recipient = response.data[0]["recipient"]

        # Send WhatsApp decline message
        message_text = (
            f"We regret to inform you that we are unable to confirm your reservation (ID: {reservation_id}) "
            "for the requested time. Our team will contact you shortly to discuss alternative options. "
            "We apologize for any inconvenience and hope to accommodate you in the future."
        )

        await runtime.async_wa_client.send_message(
            to=recipient,
            text=message_text,
        )

        logger.info(
            f"Reservation declined message sent to {recipient} for reservation {reservation_id}"
        )

        return {
            "status": "success",
            "rest_ref": rest_ref_upper,
            "reservation_id": reservation_id,
            "recipient": recipient,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing reservation decline: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
