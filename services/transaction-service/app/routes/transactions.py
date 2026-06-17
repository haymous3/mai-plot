"""/transactions route handlers — the offer flow (SCRUM-66).

POST /transactions creates an offer; the seller accepts / counters / rejects it,
and the buyer responds to a counter. Handlers are thin: build the request, call
OfferService, map domain errors to the api-contracts.md envelope.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_current_user,
    get_offer_service,
    get_transaction_status_service,
)
from app.repositories.offer_repo import OfferRow
from app.schemas.offer import CounterRequest, CreateOfferRequest, OfferResponse, RespondRequest
from app.schemas.transaction import StatusChangeRequest, StatusResponse
from app.security import CurrentUser
from app.services.offer_service import (
    AcceptResult,
    CannotOfferOwnListing,
    ListingNotAvailable,
    ListingNotFound,
    NotOfferBuyer,
    NotOfferSeller,
    OfferExpired,
    OfferNotActionable,
    OfferNotFound,
    OfferService,
)
from app.services.transaction_status import (
    InvalidStateTransition,
    NotTransactionParty,
    TransactionNotFound,
    TransactionStatusService,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


def _offer_response(offer: OfferRow, *, transaction_id: UUID | None = None) -> OfferResponse:
    return OfferResponse(
        id=offer.id,
        listing_id=offer.listing_id,
        buyer_id=offer.buyer_id,
        seller_id=offer.seller_id,
        status=offer.status,
        amount_kobo=offer.offered_price_kobo,
        counter_amount_kobo=offer.counter_price_kobo,
        expires_at=offer.expires_at,
        transaction_id=transaction_id,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OfferServiceDep = Annotated[OfferService, Depends(get_offer_service)]
StatusServiceDep = Annotated[TransactionStatusService, Depends(get_transaction_status_service)]


@router.patch("/{transaction_id}/status", response_model=StatusResponse)
async def change_status(
    transaction_id: UUID,
    body: StatusChangeRequest,
    request: Request,
    caller: CurrentUserDep,
    service: StatusServiceDep,
) -> StatusResponse | JSONResponse:
    """Move a transaction to a new stage. The state machine validates the
    transition server-side (422 on an illegal one); the Literal request type
    means a client cannot set an arbitrary stage value."""
    try:
        stage = await service.change_status(
            transaction_id=transaction_id,
            caller=caller,
            target_stage=body.status,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No transaction found.")
    except NotTransactionParty:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_TRANSACTION_PARTY",
            "You are not a party to this transaction.",
        )
    except InvalidStateTransition:
        return _error(422, "INVALID_STATE_TRANSITION", "That stage transition is not allowed.")
    return StatusResponse(transaction_id=transaction_id, stage=stage)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OfferResponse)
async def create_offer(
    body: CreateOfferRequest,
    caller: CurrentUserDep,
    service: OfferServiceDep,
) -> OfferResponse | JSONResponse:
    try:
        offer = await service.create_offer(
            buyer=caller, listing_id=body.listing_id, amount_kobo=body.amount_kobo
        )
    except ListingNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found.")
    except CannotOfferOwnListing:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "CANNOT_OFFER_OWN_LISTING",
            "You cannot make an offer on your own listing.",
        )
    except ListingNotAvailable:
        return _error(
            status.HTTP_409_CONFLICT,
            "LISTING_NOT_AVAILABLE",
            "This listing is not available for new offers.",
        )
    return _offer_response(offer)


@router.post("/{offer_id}/accept", response_model=OfferResponse)
async def accept_offer(
    offer_id: UUID,
    caller: CurrentUserDep,
    service: OfferServiceDep,
) -> OfferResponse | JSONResponse:
    try:
        result = await service.accept_offer(seller=caller, offer_id=offer_id)
    except OfferNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "OFFER_NOT_FOUND", "No offer found.")
    except NotOfferSeller:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_OFFER_SELLER", "Only the seller may decide.")
    except OfferExpired:
        return _error(status.HTTP_409_CONFLICT, "OFFER_EXPIRED", "This offer has expired.")
    except OfferNotActionable:
        return _error(
            status.HTTP_409_CONFLICT, "OFFER_NOT_ACTIONABLE", "This offer cannot be accepted."
        )
    except ListingNotAvailable:
        return _error(
            status.HTTP_409_CONFLICT,
            "LISTING_NOT_AVAILABLE",
            "This listing is no longer available.",
        )
    return _offer_response(result.offer, transaction_id=result.transaction_id)


@router.post("/{offer_id}/counter", response_model=OfferResponse)
async def counter_offer(
    offer_id: UUID,
    body: CounterRequest,
    caller: CurrentUserDep,
    service: OfferServiceDep,
) -> OfferResponse | JSONResponse:
    try:
        offer = await service.counter_offer(
            seller=caller, offer_id=offer_id, counter_amount_kobo=body.counter_amount_kobo
        )
    except OfferNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "OFFER_NOT_FOUND", "No offer found.")
    except NotOfferSeller:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_OFFER_SELLER", "Only the seller may decide.")
    except OfferExpired:
        return _error(status.HTTP_409_CONFLICT, "OFFER_EXPIRED", "This offer has expired.")
    except OfferNotActionable:
        return _error(
            status.HTTP_409_CONFLICT, "OFFER_NOT_ACTIONABLE", "This offer cannot be countered."
        )
    return _offer_response(offer)


@router.post("/{offer_id}/reject", response_model=OfferResponse)
async def reject_offer(
    offer_id: UUID,
    caller: CurrentUserDep,
    service: OfferServiceDep,
) -> OfferResponse | JSONResponse:
    try:
        offer = await service.reject_offer(seller=caller, offer_id=offer_id)
    except OfferNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "OFFER_NOT_FOUND", "No offer found.")
    except NotOfferSeller:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_OFFER_SELLER", "Only the seller may decide.")
    except OfferExpired:
        return _error(status.HTTP_409_CONFLICT, "OFFER_EXPIRED", "This offer has expired.")
    except OfferNotActionable:
        return _error(
            status.HTTP_409_CONFLICT, "OFFER_NOT_ACTIONABLE", "This offer cannot be rejected."
        )
    return _offer_response(offer)


@router.post("/{offer_id}/respond", response_model=OfferResponse)
async def respond_to_counter(
    offer_id: UUID,
    body: RespondRequest,
    caller: CurrentUserDep,
    service: OfferServiceDep,
) -> OfferResponse | JSONResponse:
    try:
        result = await service.respond_to_counter(
            buyer=caller, offer_id=offer_id, action=body.action
        )
    except OfferNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "OFFER_NOT_FOUND", "No offer found.")
    except NotOfferBuyer:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_OFFER_BUYER", "Only the buyer may respond.")
    except OfferExpired:
        return _error(status.HTTP_409_CONFLICT, "OFFER_EXPIRED", "This offer has expired.")
    except OfferNotActionable:
        return _error(
            status.HTTP_409_CONFLICT, "OFFER_NOT_ACTIONABLE", "There is no counter to respond to."
        )
    if isinstance(result, AcceptResult):
        return _offer_response(result.offer, transaction_id=result.transaction_id)
    return _offer_response(result)
